"""
Finance Dashboard — Streamlit
──────────────────────────────────────────────────────────────────────────────
Visualiza análisis de cartolas bancarias en tiempo real y permite registrar
gastos manuales, deudas y plata que te deben.

Ejecución:
  streamlit run dashboard.py
"""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR             = Path(__file__).parent
SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"
SPREADSHEET_ID       = "1sGlIewugpDLfvoXopec4UQxhFgCMbf1rQ9wgdDYxpCk"
SCOPES               = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Pestañas para datos manuales (se crean automáticamente) ───────────────────
_LOCAL_TABS = {
    "Gastos_Manuales":    ["id","fecha","descripcion","monto","moneda","categoria","metodo_pago","notas"],
    "Deudas":             ["id","tipo","nombre","descripcion","monto","moneda","fecha_origen","fecha_vencimiento","estado","notas"],
    "Ingresos_Esperados": ["id","nombre","descripcion","monto","moneda","fecha_esperada","recurrente","estado","notas"],
}

CATEGORIES = [
    "Supermercado", "Restaurante", "Combustible", "Transporte",
    "Farmacia", "Salud", "Deporte", "Entretención", "Ropa/Calzado",
    "Educación", "Servicios", "Hogar", "Mascotas",
    "Inversiones/Ahorro", "Viajes/Turismo", "Transferencias",
    "Sueldo/Salario", "Rendiciones/Reembolsos", "Otros",
]

PAYMENT_METHODS = ["Efectivo", "Débito", "Crédito", "Transferencia", "Otro"]

# ─── Paleta de colores ────────────────────────────────────────────────────────
C_GREEN  = "#2ecc71"
C_RED    = "#e74c3c"
C_BLUE   = "#3498db"
C_PURPLE = "#9b59b6"
C_GOLD   = "#f39c12"
C_TEAL   = "#1abc9c"
C_BG     = "#0f0f1a"
C_CARD   = "#1a1a2e"
C_BORDER = "#2d2d44"

# ─── Helpers de formato ───────────────────────────────────────────────────────
def fmt_clp(v: float) -> str:
    return f"${v:,.0f}"

def fmt_usd(v: float) -> str:
    return f"US${v:,.2f}"

def fmt_amount(v: float, moneda: str = "CLP") -> str:
    return fmt_clp(v) if moneda == "CLP" else fmt_usd(v)

def delta_str(current: float, previous: float) -> str:
    if previous == 0:
        return ""
    pct = (current - previous) / abs(previous) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}% vs mes anterior"

# ─── Componente KPI card ──────────────────────────────────────────────────────
def kpi_card(col, label: str, value: str, sub: str = "", color: str = C_BLUE, icon: str = ""):
    col.markdown(f"""
    <div style="background:{C_CARD};border-radius:12px;padding:18px 20px;
                border-left:4px solid {color};height:100px;">
        <div style="color:#888;font-size:11px;text-transform:uppercase;
                    letter-spacing:1.2px;margin-bottom:4px">{icon} {label}</div>
        <div style="color:#fff;font-size:22px;font-weight:700;line-height:1.2">{value}</div>
        <div style="color:{'#2ecc71' if sub.startswith('+') else '#e74c3c' if sub.startswith('-') else '#888'};
                    font-size:11px;margin-top:4px">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

# ─── Google Sheets client (cached) ───────────────────────────────────────────
@st.cache_resource
def get_sheets_service():
    """Soporta credenciales desde st.secrets (nube) o archivo local."""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds).spreadsheets()

# ─── Capa de datos: Google Sheets como base de datos ─────────────────────────
def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S%f")

def init_sheets_tabs():
    """Crea las pestañas de datos manuales si no existen."""
    svc = get_sheets_service()
    meta = svc.get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    reqs = [
        {"addSheet": {"properties": {"title": name}}}
        for name in _LOCAL_TABS if name not in existing
    ]
    if reqs:
        svc.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": reqs}).execute()
    for tab, cols in _LOCAL_TABS.items():
        result = svc.values().get(
            spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1:A1"
        ).execute()
        if not result.get("values"):
            svc.values().update(
                spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1",
                valueInputOption="RAW", body={"values": [cols]}
            ).execute()

def _read_tab(tab: str) -> pd.DataFrame:
    svc = get_sheets_service()
    result = svc.values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:Z"
    ).execute()
    rows = result.get("values", [])
    cols = _LOCAL_TABS[tab]
    if len(rows) < 2:
        return pd.DataFrame(columns=cols)
    header = rows[0]
    data   = [r + [""] * (len(header) - len(r)) for r in rows[1:]]
    return pd.DataFrame(data, columns=header)

def _write_tab(tab: str, df: pd.DataFrame):
    svc = get_sheets_service()
    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    svc.values().clear(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:Z").execute()
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1",
        valueInputOption="RAW", body={"values": values}
    ).execute()

def _append_row(tab: str, row: list):
    svc = get_sheets_service()
    svc.values().append(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:A",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [row]}
    ).execute()

# ─── Carga de datos ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_transactions() -> pd.DataFrame:
    """Carga todas las transacciones desde la pestaña 'Transacciones' de Sheets."""
    try:
        svc = get_sheets_service()
        result = svc.values().get(
            spreadsheetId=SPREADSHEET_ID, range="'Transacciones'!A:H"
        ).execute()
        rows = result.get("values", [])
    except Exception as e:
        st.warning(f"No se pudo conectar a Google Sheets: {e}")
        return pd.DataFrame()

    if not rows or len(rows) < 2:
        return pd.DataFrame()

    # Columnas: Fecha, Banco, Cuenta, Moneda, Tipo, Descripción, Categoría, Monto
    cols = ["fecha", "banco", "cuenta", "moneda", "tipo", "descripcion", "categoria", "monto"]
    data = [r + [""] * (len(cols) - len(r)) for r in rows[1:]]
    df = pd.DataFrame(data, columns=cols)

    df["fecha"]  = pd.to_datetime(df["fecha"], errors="coerce")
    df["monto"]  = pd.to_numeric(
        df["monto"].astype(str).str.replace(",", "").str.replace("$", ""), errors="coerce"
    ).fillna(0).abs()
    df["moneda"] = df["moneda"].replace("", "CLP").fillna("CLP")
    df["mes"]    = df["fecha"].dt.strftime("%Y-%m")
    df["es_gasto"] = df["tipo"] != "Ingreso"
    df = df.dropna(subset=["fecha"])
    return df


@st.cache_data(ttl=60)
def load_gastos_manuales() -> pd.DataFrame:
    df = _read_tab("Gastos_Manuales")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["mes"]   = df["fecha"].dt.strftime("%Y-%m")
        df = df.sort_values("fecha", ascending=False)
    return df


@st.cache_data(ttl=30)
def load_deudas() -> pd.DataFrame:
    df = _read_tab("Deudas")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.sort_values(["estado", "fecha_origen"], ascending=[True, False])
    return df


@st.cache_data(ttl=30)
def load_ingresos_esperados() -> pd.DataFrame:
    df = _read_tab("Ingresos_Esperados")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.sort_values("fecha_esperada")
    return df

# ─── Configuración de tema ────────────────────────────────────────────────────
GLOBAL_CSS = f"""
<style>
    .stApp {{ background-color: {C_BG}; color: #e0e0e0; }}
    section[data-testid="stSidebar"] {{ background-color: {C_CARD}; border-right: 1px solid {C_BORDER}; }}
    .stButton > button {{ border-radius: 8px; border: 1px solid {C_BORDER}; background: {C_CARD}; color: #fff; }}
    .stButton > button:hover {{ background: {C_BORDER}; border-color: #555; }}
    .stDataFrame {{ border-radius: 8px; }}
    div[data-testid="stMetric"] label {{ color: #888 !important; }}
    h1 {{ color: #fff !important; margin-bottom: 0.5rem !important; }}
    h2, h3 {{ color: #ddd !important; }}
    .stTabs [data-baseweb="tab"] {{ color: #aaa; }}
    .stTabs [aria-selected="true"] {{ color: #fff !important; }}
    .stAlert {{ border-radius: 8px; }}
    .block-container {{ padding-top: 1.5rem; }}
    hr {{ border-color: {C_BORDER}; }}
</style>
"""

# ─── Chart helpers ────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#ccc",
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", font_color="#ccc"),
    xaxis=dict(gridcolor="#2d2d44", zerolinecolor="#2d2d44"),
    yaxis=dict(gridcolor="#2d2d44", zerolinecolor="#2d2d44"),
)

def apply_layout(fig, **extra):
    fig.update_layout(**{**CHART_LAYOUT, **extra})
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#   PÁGINAS
# ══════════════════════════════════════════════════════════════════════════════

# ─── 1. DASHBOARD ─────────────────────────────────────────────────────────────
def page_dashboard():
    st.title("📊 Dashboard")

    df      = load_transactions()
    df_man  = load_gastos_manuales()
    df_deu  = load_deudas()

    if df.empty:
        st.warning("Sin datos de cartolas. Ejecuta `python main.py` primero.")
        return

    df_clp = df[df["moneda"] == "CLP"]
    all_months = sorted(df_clp["mes"].dropna().unique(), reverse=True)

    # ── Selector de mes ───────────────────────────────────────────────────────
    col_sel, _ = st.columns([1, 3])
    sel_month  = col_sel.selectbox("Mes activo", all_months, index=0)
    prev_month = all_months[1] if len(all_months) > 1 else None

    def month_kpis(month):
        dm = df_clp[df_clp["mes"] == month]
        gastos   = dm[dm["es_gasto"]]["monto"].sum()
        ingresos = dm[~dm["es_gasto"]]["monto"].sum()
        manual   = df_man[df_man["mes"] == month]["monto"].sum() if not df_man.empty else 0
        gastos  += manual
        balance  = ingresos - gastos
        ahorro   = balance / ingresos * 100 if ingresos > 0 else 0
        sueldo   = dm[dm["categoria"] == "Sueldo/Salario"]["monto"].sum()
        return gastos, ingresos, balance, ahorro, sueldo

    g, i, b, a, s    = month_kpis(sel_month)
    gp, ip, bp, ap, sp = month_kpis(prev_month) if prev_month else (0, 0, 0, 0, 0)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "Ingresos",  fmt_clp(i), delta_str(i, ip),  C_GREEN,  "↑")
    kpi_card(c2, "Gastos",    fmt_clp(g), delta_str(g, gp),  C_RED,    "↓")
    kpi_card(c3, "Balance",   fmt_clp(b), delta_str(b, bp),
             C_GREEN if b >= 0 else C_RED, "=" )
    kpi_card(c4, "Ahorro",    f"{a:.1f}%", delta_str(a, ap), C_PURPLE, "💰")
    kpi_card(c5, "Sueldo",    fmt_clp(s), "",                C_GOLD,   "🏦")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Deudas pendientes (alerta rápida) ─────────────────────────────────────
    if not df_deu.empty:
        pend = df_deu[df_deu["estado"] == "pendiente"]
        if not pend.empty:
            me_deben = pend[pend["tipo"] == "me_deben"]["monto"].sum()
            debo     = pend[pend["tipo"] == "debo"]["monto"].sum()
            da, db   = st.columns(2)
            if me_deben > 0:
                da.success(f"💰 **Me deben:** {fmt_clp(me_deben)} — {len(pend[pend['tipo']=='me_deben'])} pendientes")
            if debo > 0:
                db.warning(f"📤 **Debo:** {fmt_clp(debo)} — {len(pend[pend['tipo']=='debo'])} pendientes")

    # ── Charts ────────────────────────────────────────────────────────────────
    dm_sel = df_clp[df_clp["mes"] == sel_month]
    gastos_m = dm_sel[dm_sel["es_gasto"]]

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.subheader("Gastos por categoría")
        by_cat = gastos_m.groupby("categoria")["monto"].sum().sort_values()
        if not by_cat.empty:
            fig = go.Figure(go.Bar(
                x=by_cat.values, y=by_cat.index, orientation="h",
                marker=dict(color=by_cat.values, colorscale="Reds", showscale=False),
                text=[fmt_clp(v) for v in by_cat.values], textposition="outside",
            ))
            apply_layout(fig, height=350, xaxis_tickformat="$,.0f",
                         yaxis=dict(gridcolor="#2d2d44"))
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Distribución")
        by_cat_pie = gastos_m.groupby("categoria")["monto"].sum()
        if not by_cat_pie.empty:
            fig = px.pie(values=by_cat_pie.values, names=by_cat_pie.index,
                         hole=0.48, color_discrete_sequence=px.colors.qualitative.Set2)
            apply_layout(fig, height=350,
                         legend=dict(orientation="v", x=1.02, y=0.5,
                                     bgcolor="rgba(0,0,0,0)", font_color="#ccc"))
            fig.update_traces(textfont_color="#fff", textinfo="percent")
            st.plotly_chart(fig, use_container_width=True)

    # ── Transacciones recientes ───────────────────────────────────────────────
    st.subheader("Transacciones recientes")
    recent = dm_sel.sort_values("fecha", ascending=False).head(15)
    if not recent.empty:
        disp = recent[["fecha", "banco", "descripcion", "categoria", "tipo", "monto"]].copy()
        disp["fecha"]  = disp["fecha"].dt.strftime("%d/%m/%Y")
        disp["monto"]  = disp.apply(lambda r: fmt_clp(r["monto"]), axis=1)
        disp["tipo"]   = disp["tipo"].apply(lambda t: "🟢 Ingreso" if t == "Ingreso" else "🔴 Gasto")
        st.dataframe(disp.rename(columns={"fecha": "Fecha", "banco": "Banco",
                                          "descripcion": "Descripción",
                                          "categoria": "Categoría",
                                          "tipo": "Tipo", "monto": "Monto"}),
                     hide_index=True, use_container_width=True, height=400)


# ─── 2. TRANSACCIONES ─────────────────────────────────────────────────────────
def page_transacciones():
    st.title("💳 Transacciones")

    df = load_transactions()
    if df.empty:
        st.warning("Sin datos.")
        return

    # ── Filtros ───────────────────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=True):
        f1, f2, f3, f4, f5 = st.columns(5)

        all_months = sorted(df["mes"].dropna().unique(), reverse=True)
        sel_months = f1.multiselect("Mes", all_months, default=[all_months[0]] if all_months else [])

        all_cats  = ["(Todas)"] + sorted(df["categoria"].dropna().unique())
        sel_cat   = f2.selectbox("Categoría", all_cats)

        all_banks = ["(Todos)"] + sorted(df["banco"].dropna().unique())
        sel_bank  = f3.selectbox("Banco", all_banks)

        sel_tipo  = f4.selectbox("Tipo", ["Todos", "Gasto", "Ingreso"])
        search    = f5.text_input("Buscar")

    filt = df.copy()
    if sel_months:
        filt = filt[filt["mes"].isin(sel_months)]
    if sel_cat != "(Todas)":
        filt = filt[filt["categoria"] == sel_cat]
    if sel_bank != "(Todos)":
        filt = filt[filt["banco"] == sel_bank]
    if sel_tipo == "Gasto":
        filt = filt[filt["es_gasto"]]
    elif sel_tipo == "Ingreso":
        filt = filt[~filt["es_gasto"]]
    if search:
        filt = filt[filt["descripcion"].str.contains(search, case=False, na=False)]

    # ── Métricas rápidas ──────────────────────────────────────────────────────
    g_tot = filt[filt["es_gasto"] & (filt["moneda"] == "CLP")]["monto"].sum()
    i_tot = filt[~filt["es_gasto"] & (filt["moneda"] == "CLP")]["monto"].sum()
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Transacciones", len(filt))
    mc2.metric("Total gastos CLP",   fmt_clp(g_tot))
    mc3.metric("Total ingresos CLP", fmt_clp(i_tot))

    # ── Tabla ─────────────────────────────────────────────────────────────────
    disp = filt.sort_values("fecha", ascending=False).copy()
    disp["fecha"] = disp["fecha"].dt.strftime("%d/%m/%Y")
    disp["monto_fmt"] = disp.apply(
        lambda r: (fmt_clp if r["moneda"] == "CLP" else fmt_usd)(r["monto"]), axis=1
    )
    disp["tipo"] = disp["tipo"].apply(lambda t: "🟢 Ingreso" if t == "Ingreso" else "🔴 Gasto")

    st.dataframe(
        disp[["fecha", "banco", "cuenta", "descripcion", "categoria",
              "tipo", "monto_fmt", "moneda"]].rename(
            columns={"fecha": "Fecha", "banco": "Banco", "cuenta": "Cuenta",
                     "descripcion": "Descripción", "categoria": "Categoría",
                     "tipo": "Tipo", "monto_fmt": "Monto", "moneda": "Moneda"}
        ),
        hide_index=True, use_container_width=True, height=550,
    )


# ─── 3. GASTOS MANUALES ───────────────────────────────────────────────────────
def page_gastos_manuales():
    st.title("✏️ Gastos Manuales")
    st.caption("Registra gastos en efectivo o cualquier gasto que no aparezca en tus cartolas.")

    tab_new, tab_list, tab_stats = st.tabs(["➕ Nuevo gasto", "📋 Historial", "📊 Estadísticas"])

    # ── Formulario nuevo gasto ────────────────────────────────────────────────
    with tab_new:
        with st.form("form_gasto", clear_on_submit=True):
            c1, c2 = st.columns(2)
            fecha   = c1.date_input("Fecha", value=date.today())
            monto   = c2.number_input("Monto *", min_value=0.0, step=500.0, format="%.0f")

            descripcion = st.text_input("Descripción *", placeholder="Ej: Almuerzo con clientes")

            c3, c4, c5 = st.columns(3)
            moneda      = c3.selectbox("Moneda", ["CLP", "USD"])
            categoria   = c4.selectbox("Categoría", CATEGORIES)
            metodo_pago = c5.selectbox("Método de pago", PAYMENT_METHODS)

            notas = st.text_area("Notas", height=80, placeholder="Opcional")

            submitted = st.form_submit_button("💾 Guardar gasto", type="primary", use_container_width=True)

        if submitted:
            if not descripcion:
                st.error("La descripción es obligatoria.")
            elif monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                _append_row("Gastos_Manuales", [
                    _new_id(), fecha.isoformat(), descripcion, monto,
                    moneda, categoria, metodo_pago, notas or ""
                ])
                st.success(f"✅ Guardado: **{descripcion}** — {fmt_amount(monto, moneda)}")
                st.cache_data.clear()

    # ── Historial ─────────────────────────────────────────────────────────────
    with tab_list:
        df = load_gastos_manuales()
        if df.empty:
            st.info("No hay gastos manuales registrados aún.")
        else:
            # Filtros
            hf1, hf2 = st.columns(2)
            all_m = ["Todos"] + sorted(df["mes"].unique(), reverse=True)
            sel_m = hf1.selectbox("Mes", all_m, key="gm_mes")
            all_c = ["Todas"] + sorted(df["categoria"].unique())
            sel_c = hf2.selectbox("Categoría", all_c, key="gm_cat")

            filt = df.copy()
            if sel_m != "Todos":
                filt = filt[filt["mes"] == sel_m]
            if sel_c != "Todas":
                filt = filt[filt["categoria"] == sel_c]

            total = filt["monto"].sum()
            st.markdown(f"**{len(filt)} registros** — Total: **{fmt_clp(total)}**")

            for _, row in filt.iterrows():
                with st.container():
                    rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([1.5, 3, 2, 2, 1.5, 0.5])
                    rc1.write(row["fecha"].strftime("%d/%m/%Y") if pd.notna(row["fecha"]) else "—")
                    rc2.write(row["descripcion"])
                    rc3.write(row["categoria"])
                    rc4.write(row["metodo_pago"])
                    rc5.write(fmt_amount(row["monto"], row["moneda"]))
                    if rc6.button("🗑️", key=f"del_gm_{row['id']}", help="Eliminar"):
                        df_all = load_gastos_manuales()
                        _write_tab("Gastos_Manuales", df_all[df_all["id"] != row["id"]].drop(columns=["mes"], errors="ignore"))
                        st.cache_data.clear()
                        st.rerun()

    # ── Estadísticas gastos manuales ──────────────────────────────────────────
    with tab_stats:
        df = load_gastos_manuales()
        if df.empty or len(df) < 2:
            st.info("Registra más gastos para ver estadísticas.")
        else:
            by_cat = df.groupby("categoria")["monto"].sum().sort_values(ascending=False)
            fig = px.bar(x=by_cat.index, y=by_cat.values,
                         labels={"x": "Categoría", "y": "CLP"},
                         color=by_cat.values, color_continuous_scale="Blues",
                         title="Gastos manuales por categoría")
            apply_layout(fig, coloraxis_showscale=False, yaxis_tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

            by_method = df.groupby("metodo_pago")["monto"].sum()
            fig2 = px.pie(values=by_method.values, names=by_method.index,
                          hole=0.4, title="Por método de pago",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            apply_layout(fig2)
            st.plotly_chart(fig2, use_container_width=True)


# ─── 4. DEUDAS ────────────────────────────────────────────────────────────────
def _render_debt_section(df_d: pd.DataFrame, tipo_key: str):
    if df_d.empty:
        st.info("No hay registros.")
        return

    pending = df_d[df_d["estado"] == "pendiente"]
    paid    = df_d[df_d["estado"] == "pagado"]
    total_p = pending["monto"].sum() if not pending.empty else 0

    color = C_GREEN if tipo_key == "me_deben" else C_RED
    st.markdown(
        f'<div style="background:{C_CARD};border-radius:10px;padding:14px 18px;'
        f'border-left:4px solid {color};margin-bottom:16px">'
        f'<span style="color:#aaa;font-size:11px;text-transform:uppercase">Total pendiente</span><br>'
        f'<span style="color:#fff;font-size:24px;font-weight:700">{fmt_clp(total_p)}</span>'
        f'<span style="color:#888;font-size:13px;margin-left:12px">'
        f'{len(pending)} registros</span></div>',
        unsafe_allow_html=True
    )

    if not pending.empty:
        for _, row in pending.iterrows():
            with st.container():
                rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([2, 3, 1.5, 2, 0.8, 0.8])
                rc1.write(f"**{row['nombre']}**")
                rc2.write(row.get("descripcion") or "—")
                rc3.write(fmt_amount(row["monto"], row.get("moneda", "CLP")))

                venc = row.get("fecha_vencimiento")
                if venc and str(venc) not in ("None", "nan", "", "NaT"):
                    try:
                        days = (datetime.fromisoformat(str(venc)[:10]) - datetime.now()).days
                        if days < 0:
                            rc4.error(f"⚠️ Vencido hace {-days}d")
                        elif days < 7:
                            rc4.warning(f"⏰ Vence en {days}d")
                        else:
                            rc4.write(str(venc)[:10])
                    except Exception:
                        rc4.write(str(venc)[:10])
                else:
                    rc4.write("Sin vencimiento")

                if rc5.button("✅", key=f"pay_{tipo_key}_{row['id']}", help="Marcar pagado"):
                    df_all = load_deudas()
                    df_all.loc[df_all["id"] == row["id"], "estado"] = "pagado"
                    _write_tab("Deudas", df_all)
                    st.cache_data.clear()
                    st.rerun()

                if rc6.button("🗑️", key=f"del_{tipo_key}_{row['id']}", help="Eliminar"):
                    df_all = load_deudas()
                    _write_tab("Deudas", df_all[df_all["id"] != row["id"]])
                    st.cache_data.clear()
                    st.rerun()

    if not paid.empty:
        with st.expander(f"Historial pagadas / saldadas ({len(paid)})"):
            for _, row in paid.iterrows():
                rc1, rc2, rc3, rc4 = st.columns([2, 3, 2, 0.8])
                rc1.markdown(f"~~{row['nombre']}~~")
                rc2.write(row.get("descripcion") or "—")
                rc3.write(fmt_amount(row["monto"], row.get("moneda", "CLP")))
                if rc4.button("🗑️", key=f"delpaid_{tipo_key}_{row['id']}"):
                    df_all = load_deudas()
                    _write_tab("Deudas", df_all[df_all["id"] != row["id"]])
                    st.cache_data.clear()
                    st.rerun()


def page_deudas():
    st.title("💳 Deudas & Pendientes")

    df_deu = load_deudas()

    # ── Resumen rápido ────────────────────────────────────────────────────────
    if not df_deu.empty:
        pend = df_deu[df_deu["estado"] == "pendiente"]
        me_deben = pend[pend["tipo"] == "me_deben"]["monto"].sum() if not pend.empty else 0
        debo     = pend[pend["tipo"] == "debo"]["monto"].sum()     if not pend.empty else 0
        neto     = me_deben - debo
        sc1, sc2, sc3 = st.columns(3)
        kpi_card(sc1, "Me deben",   fmt_clp(me_deben), "", C_GREEN,  "💰")
        kpi_card(sc2, "Debo",       fmt_clp(debo),     "", C_RED,    "📤")
        kpi_card(sc3, "Neto",       fmt_clp(neto),     "",
                 C_GREEN if neto >= 0 else C_RED, "⚖️")
        st.markdown("<br>", unsafe_allow_html=True)

    tab_add, tab_me_deben, tab_debo, tab_esperados = st.tabs(
        ["➕ Registrar", "💰 Me deben", "📤 Debo", "🔜 Ingresos esperados"]
    )

    # ── Formulario nueva deuda ────────────────────────────────────────────────
    with tab_add:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Nueva deuda / préstamo")
            with st.form("form_deuda", clear_on_submit=True):
                tipo_label = st.radio("¿Quién debe?", ["Me deben a mí", "Yo le debo a alguien"], horizontal=True)
                tipo_val   = "me_deben" if tipo_label == "Me deben a mí" else "debo"

                d1, d2 = st.columns(2)
                nombre = d1.text_input("Nombre / Concepto *")
                monto  = d2.number_input("Monto *", min_value=0.0, step=1000.0, format="%.0f")

                descripcion = st.text_input("Descripción")

                d3, d4, d5 = st.columns(3)
                moneda            = d3.selectbox("Moneda", ["CLP", "USD"])
                fecha_origen      = d4.date_input("Fecha origen", value=date.today())
                fecha_vencimiento = d5.date_input("Fecha límite", value=None)

                notas = st.text_area("Notas", height=70)

                if st.form_submit_button("💾 Registrar", type="primary", use_container_width=True):
                    if not nombre:
                        st.error("El nombre es obligatorio.")
                    elif monto <= 0:
                        st.error("El monto debe ser mayor a 0.")
                    else:
                        _append_row("Deudas", [
                            _new_id(), tipo_val, nombre, descripcion or "", monto, moneda,
                            fecha_origen.isoformat(),
                            fecha_vencimiento.isoformat() if fecha_vencimiento else "",
                            "pendiente", notas or ""
                        ])
                        st.success(f"✅ Registrado: {nombre} — {fmt_amount(monto, moneda)}")
                        st.cache_data.clear()
                        st.rerun()

        with col_b:
            st.subheader("Nuevo ingreso esperado")
            with st.form("form_ingreso_esp", clear_on_submit=True):
                ie1, ie2 = st.columns(2)
                ie_nombre = ie1.text_input("Concepto *")
                ie_monto  = ie2.number_input("Monto *", min_value=0.0, step=1000.0, format="%.0f")
                ie_desc   = st.text_input("Descripción")
                ie3, ie4, ie5 = st.columns(3)
                ie_moneda    = ie3.selectbox("Moneda", ["CLP", "USD"], key="ie_mon")
                ie_fecha     = ie4.date_input("Fecha esperada", key="ie_fecha")
                ie_recurrente = ie5.checkbox("Mensual recurrente")
                ie_notas = st.text_area("Notas", height=70, key="ie_notas")

                if st.form_submit_button("💾 Guardar", type="primary", use_container_width=True):
                    if not ie_nombre or ie_monto <= 0:
                        st.error("Nombre y monto son obligatorios.")
                    else:
                        _append_row("Ingresos_Esperados", [
                            _new_id(), ie_nombre, ie_desc or "", ie_monto, ie_moneda,
                            ie_fecha.isoformat(), int(ie_recurrente), "pendiente", ie_notas or ""
                        ])
                        st.success(f"✅ Guardado: {ie_nombre}")
                        st.cache_data.clear()
                        st.rerun()

    with tab_me_deben:
        st.subheader("💰 Dinero que me deben")
        _render_debt_section(
            df_deu[df_deu["tipo"] == "me_deben"] if not df_deu.empty else pd.DataFrame(),
            "me_deben"
        )

    with tab_debo:
        st.subheader("📤 Dinero que le debo a otros")
        _render_debt_section(
            df_deu[df_deu["tipo"] == "debo"] if not df_deu.empty else pd.DataFrame(),
            "debo"
        )

    with tab_esperados:
        st.subheader("🔜 Ingresos esperados / por recibir")
        df_ie = load_ingresos_esperados()
        if df_ie.empty:
            st.info("No hay ingresos esperados registrados.")
        else:
            pend_ie = df_ie[df_ie["estado"] == "pendiente"]
            total_ie = pend_ie["monto"].sum() if not pend_ie.empty else 0
            st.markdown(f"**Total esperado: {fmt_clp(total_ie)}**")

            for _, row in df_ie.iterrows():
                with st.container():
                    rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([2, 3, 2, 2, 0.8, 0.8])
                    rc1.write(f"{'🟡' if row['estado']=='pendiente' else '✅'} **{row['nombre']}**")
                    rc2.write(row.get("descripcion") or "—")
                    rc3.write(fmt_amount(row["monto"], row.get("moneda", "CLP")))
                    fe = row.get("fecha_esperada")
                    rc4.write(str(fe)[:10] if fe else "—")

                    if row["estado"] == "pendiente":
                        if rc5.button("✅", key=f"ie_pay_{row['id']}", help="Marcar recibido"):
                            df_all = load_ingresos_esperados()
                            df_all.loc[df_all["id"] == row["id"], "estado"] = "recibido"
                            _write_tab("Ingresos_Esperados", df_all)
                            st.cache_data.clear()
                            st.rerun()

                    if rc6.button("🗑️", key=f"ie_del_{row['id']}"):
                        df_all = load_ingresos_esperados()
                        _write_tab("Ingresos_Esperados", df_all[df_all["id"] != row["id"]])
                        st.cache_data.clear()
                        st.rerun()


# ─── 5. HISTÓRICO ─────────────────────────────────────────────────────────────
def page_historico():
    st.title("📈 Histórico Comparativo")

    df = load_transactions()
    if df.empty:
        st.warning("Sin datos.")
        return

    df_clp = df[df["moneda"] == "CLP"]
    df_man = load_gastos_manuales()

    # ── Construir resumen mensual ──────────────────────────────────────────────
    ing = df_clp[~df_clp["es_gasto"]].groupby("mes")["monto"].sum().rename("Ingresos")
    gst = df_clp[df_clp["es_gasto"]].groupby("mes")["monto"].sum().rename("Gastos")
    monthly = pd.concat([ing, gst], axis=1).fillna(0).reset_index().sort_values("mes")

    # Sumar gastos manuales por mes
    if not df_man.empty:
        man_m = df_man.groupby("mes")["monto"].sum().rename("GastosManual")
        monthly = monthly.join(man_m, on="mes", how="left").fillna(0)
        monthly["Gastos"] += monthly["GastosManual"]

    monthly["Balance"] = monthly["Ingresos"] - monthly["Gastos"]
    monthly["Ahorro%"] = (monthly["Balance"] / monthly["Ingresos"].replace(0, 1) * 100).round(1)
    monthly["mes_label"] = monthly["mes"]

    if monthly.empty:
        st.info("No hay datos suficientes.")
        return

    # ── Selector de rango ─────────────────────────────────────────────────────
    all_months = sorted(monthly["mes"].unique())
    if len(all_months) > 1:
        rf1, rf2 = st.columns(2)
        start_m = rf1.selectbox("Desde", all_months, index=0)
        end_m   = rf2.selectbox("Hasta", all_months, index=len(all_months)-1)
        monthly = monthly[(monthly["mes"] >= start_m) & (monthly["mes"] <= end_m)]

    # ── Gráfico 1 & 2: Ingresos/Gastos y Balance ─────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ingresos vs Gastos")
        fig = go.Figure()
        fig.add_bar(name="Ingresos", x=monthly["mes"], y=monthly["Ingresos"],
                    marker_color=C_GREEN, text=monthly["Ingresos"].apply(lambda v: f"${v/1e6:.1f}M"),
                    textposition="outside")
        fig.add_bar(name="Gastos", x=monthly["mes"], y=monthly["Gastos"],
                    marker_color=C_RED, text=monthly["Gastos"].apply(lambda v: f"${v/1e6:.1f}M"),
                    textposition="outside")
        apply_layout(fig, barmode="group", height=340, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Balance mensual")
        colors = [C_GREEN if v >= 0 else C_RED for v in monthly["Balance"]]
        fig = go.Figure(go.Bar(
            x=monthly["mes"], y=monthly["Balance"], marker_color=colors,
            text=monthly["Balance"].apply(lambda v: f"${v/1e6:.1f}M"), textposition="outside"
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#555")
        apply_layout(fig, height=340, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

    # ── Gráfico 3 & 4: Ahorro% y Gastos por categoría ─────────────────────────
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Tasa de ahorro %")
        fig = go.Figure()
        fig.add_scatter(x=monthly["mes"], y=monthly["Ahorro%"],
                        mode="lines+markers+text",
                        line=dict(color=C_PURPLE, width=2),
                        marker=dict(size=8, color=C_PURPLE),
                        text=monthly["Ahorro%"].apply(lambda v: f"{v:.0f}%"),
                        textposition="top center")
        fig.add_hline(y=0, line_dash="dash", line_color="#555")
        apply_layout(fig, height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.subheader("Gastos por categoría (stacked)")
        cat_m = df_clp[df_clp["es_gasto"]].copy()
        if not df_man.empty:
            man_cat = df_man[["mes", "categoria", "monto"]].copy()
            cat_m = pd.concat([cat_m[["mes", "categoria", "monto"]], man_cat], ignore_index=True)
        cat_m = cat_m.groupby(["mes", "categoria"])["monto"].sum().reset_index()
        if not cat_m.empty:
            # Filter to selected months
            if len(all_months) > 1:
                cat_m = cat_m[(cat_m["mes"] >= start_m) & (cat_m["mes"] <= end_m)]
            fig = px.bar(cat_m, x="mes", y="monto", color="categoria",
                         barmode="stack",
                         labels={"monto": "CLP", "mes": "Mes", "categoria": "Categoría"},
                         color_discrete_sequence=px.colors.qualitative.Set2)
            apply_layout(fig, height=340, yaxis_tickformat="$,.0f",
                         legend=dict(orientation="v", x=1.02, y=0.5,
                                     bgcolor="rgba(0,0,0,0)", font_color="#ccc"))
            st.plotly_chart(fig, use_container_width=True)

    # ── Heatmap: gasto por categoría × mes ────────────────────────────────────
    st.subheader("Mapa de calor — Gasto por categoría")
    cat_pivot = df_clp[df_clp["es_gasto"]].groupby(["mes", "categoria"])["monto"].sum()
    if not cat_pivot.empty:
        heat = cat_pivot.unstack(fill_value=0)
        fig = px.imshow(
            heat.T,
            labels=dict(x="Mes", y="Categoría", color="CLP"),
            color_continuous_scale="Reds",
            aspect="auto",
            text_auto=".3s",
        )
        apply_layout(fig, height=max(300, len(heat.columns) * 30),
                     coloraxis_colorbar=dict(tickformat="$,.0f"))
        fig.update_traces(textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)

    # ── Tabla resumen mensual ─────────────────────────────────────────────────
    st.subheader("Tabla resumen")
    tbl = monthly[["mes", "Ingresos", "Gastos", "Balance", "Ahorro%"]].copy()
    tbl["Ingresos"] = tbl["Ingresos"].apply(fmt_clp)
    tbl["Gastos"]   = tbl["Gastos"].apply(fmt_clp)
    tbl["Balance"]  = tbl["Balance"].apply(fmt_clp)
    tbl["Ahorro%"]  = tbl["Ahorro%"].apply(lambda v: f"{v:.1f}%")
    st.dataframe(tbl.rename(columns={"mes": "Mes"}),
                 hide_index=True, use_container_width=True)


# ─── 6. ANÁLISIS AI ───────────────────────────────────────────────────────────
def page_analisis():
    st.title("🤖 Análisis IA")

    df = load_transactions()
    if df.empty:
        st.warning("Sin datos de transacciones.")
        return

    all_months = sorted(df["mes"].dropna().unique(), reverse=True)
    sel_month  = st.selectbox("Mes a analizar", all_months)

    dm = df[df["mes"] == sel_month]
    df_clp = dm[dm["moneda"] == "CLP"]
    gastos   = df_clp[df_clp["es_gasto"]]
    ingresos = df_clp[~df_clp["es_gasto"]]

    total_g = gastos["monto"].sum()
    total_i = ingresos["monto"].sum()
    by_cat  = gastos.groupby("categoria")["monto"].sum().sort_values(ascending=False)

    context = f"""Período: {sel_month}
Total ingresos CLP: ${total_i:,.0f}
Total gastos CLP: ${total_g:,.0f}
Balance: ${total_i - total_g:,.0f}
Ahorro: {(total_i - total_g) / total_i * 100:.1f}% si hay ingresos

Gastos por categoría:
{chr(10).join(f"  {c}: ${v:,.0f} ({v/total_g*100:.1f}%)" for c, v in by_cat.items() if total_g > 0)}

Top 10 gastos individuales:
{chr(10).join(f"  {r['descripcion'][:50]}: ${r['monto']:,.0f}" for _, r in gastos.nlargest(10, 'monto').iterrows())}
"""

    st.text_area("Contexto financiero del mes", context, height=250)

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Top categorías")
        if not by_cat.empty:
            fig = go.Figure(go.Bar(
                x=by_cat.values, y=by_cat.index, orientation="h",
                marker=dict(color=by_cat.values, colorscale="Oranges", showscale=False),
                text=[f"{v/total_g*100:.0f}%" for v in by_cat.values], textposition="outside",
            ))
            apply_layout(fig, height=320, xaxis_tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Evolución diaria de gastos")
        daily = gastos.groupby(gastos["fecha"].dt.date)["monto"].sum().reset_index()
        daily.columns = ["fecha", "monto"]
        if not daily.empty:
            fig = px.area(daily, x="fecha", y="monto",
                          color_discrete_sequence=[C_RED])
            apply_layout(fig, height=320, yaxis_tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

    # ── Panel de presupuesto ──────────────────────────────────────────────────
    st.subheader("🎯 Comparar con presupuesto")
    st.caption("Define tu presupuesto mensual por categoría y mira cuánto te queda.")

    budget_cats = ["Supermercado", "Restaurante", "Combustible", "Entretención",
                   "Ropa/Calzado", "Salud", "Transporte", "Servicios"]

    budget_cols = st.columns(4)
    budgets = {}
    for idx, cat in enumerate(budget_cats):
        gastado = by_cat.get(cat, 0)
        budgets[cat] = budget_cols[idx % 4].number_input(
            f"{cat}", value=int(gastado * 1.2), step=10000, format="%d", key=f"bud_{cat}"
        )

    st.markdown("#### Progreso vs presupuesto")
    prog_cols = st.columns(4)
    for idx, cat in enumerate(budget_cats):
        gastado   = by_cat.get(cat, 0)
        presupuesto = budgets[cat]
        pct = (gastado / presupuesto * 100) if presupuesto > 0 else 0
        color = "🟢" if pct < 80 else "🟡" if pct < 100 else "🔴"
        with prog_cols[idx % 4]:
            st.caption(f"{color} **{cat}**")
            st.progress(min(pct / 100, 1.0))
            st.caption(f"{fmt_clp(gastado)} / {fmt_clp(presupuesto)} ({pct:.0f}%)")


# ══════════════════════════════════════════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    st.set_page_config(
        page_title="Mis Finanzas",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    init_sheets_tabs()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:12px 0 20px">
            <div style="font-size:36px">💰</div>
            <div style="font-size:18px;font-weight:700;color:#fff">Mis Finanzas</div>
            <div style="font-size:11px;color:#888">Panel de control personal</div>
        </div>
        """, unsafe_allow_html=True)

        PAGES = {
            "🏠  Dashboard":           page_dashboard,
            "💳  Transacciones":        page_transacciones,
            "✏️   Gastos Manuales":     page_gastos_manuales,
            "📊  Deudas & Pendientes":  page_deudas,
            "📈  Histórico":            page_historico,
            "🤖  Análisis & Presupuesto": page_analisis,
        }

        page_key = st.radio("Navegación", list(PAGES.keys()), label_visibility="collapsed")

        st.markdown("---")

        df = load_transactions()
        if not df.empty:
            last_date = df["fecha"].max()
            n_tx      = len(df)
            n_months  = df["mes"].nunique()
            st.markdown(f"""
            <div style="background:{C_CARD};border-radius:8px;padding:12px;font-size:12px;color:#aaa">
                📅 Última carga: <b style="color:#ddd">{last_date.strftime('%d/%m/%Y')}</b><br>
                📝 Transacciones: <b style="color:#ddd">{n_tx:,}</b><br>
                🗓️ Meses con datos: <b style="color:#ddd">{n_months}</b>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄  Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.caption("Datos de cartolas: ejecuta `python main.py`")

    # ── Render page ───────────────────────────────────────────────────────────
    PAGES[page_key]()


if __name__ == "__main__":
    main()
