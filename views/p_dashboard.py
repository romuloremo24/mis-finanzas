"""Página: Dashboard principal con KPIs del mes activo."""
import streamlit as st

from utils.config import C_GREEN, C_RED, C_BLUE, C_PURPLE, C_GOLD, C_CARD
from utils.loaders import load_transactions, load_gastos_manuales, load_deudas
from utils.ui import fmt_clp, fmt_amount, delta_str, kpi_card, apply_layout, download_csv
import plotly.express as px
import plotly.graph_objects as go


def render():
    st.title("📊 Dashboard")

    df     = load_transactions()
    df_man = load_gastos_manuales()
    df_deu = load_deudas()

    if df.empty:
        st.warning("Sin datos de cartolas. Ejecuta `python main.py` o importa desde **Importar Cartola**.")
        return

    df_clp     = df[df["moneda"] == "CLP"]
    all_months = sorted(df_clp["mes"].dropna().unique(), reverse=True)

    col_sel, _ = st.columns([1, 3])
    sel_month  = col_sel.selectbox("Mes activo", all_months, index=0)
    prev_month = all_months[1] if len(all_months) > 1 else None

    def month_kpis(month):
        dm       = df_clp[df_clp["mes"] == month]
        gastos   = dm[dm["es_gasto"]]["monto"].sum()
        ingresos = dm[~dm["es_gasto"]]["monto"].sum()
        manual   = df_man[df_man["mes"] == month]["monto"].sum() if not df_man.empty else 0
        gastos  += manual
        balance  = ingresos - gastos
        ahorro   = balance / ingresos * 100 if ingresos > 0 else 0
        sueldo   = dm[dm["categoria"] == "Sueldo/Salario"]["monto"].sum()
        return gastos, ingresos, balance, ahorro, sueldo

    g, i, b, a, s        = month_kpis(sel_month)
    gp, ip, bp, ap, sp   = month_kpis(prev_month) if prev_month else (0, 0, 0, 0, 0)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "Ingresos", fmt_clp(i), delta_str(i, ip), C_GREEN,  "↑")
    kpi_card(c2, "Gastos",   fmt_clp(g), delta_str(g, gp), C_RED,    "↓")
    kpi_card(c3, "Balance",  fmt_clp(b), delta_str(b, bp),
             C_GREEN if b >= 0 else C_RED, "=")
    kpi_card(c4, "Ahorro",   f"{a:.1f}%", delta_str(a, ap), C_PURPLE, "💰")
    kpi_card(c5, "Sueldo",   fmt_clp(s), "",                C_GOLD,   "🏦")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Alertas de deudas ─────────────────────────────────────────────────────
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
    dm_sel  = df_clp[df_clp["mes"] == sel_month]
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
        disp["fecha"] = disp["fecha"].dt.strftime("%d/%m/%Y")
        disp["monto"] = disp.apply(lambda r: fmt_clp(r["monto"]), axis=1)
        disp["tipo"]  = disp["tipo"].apply(lambda t: "🟢 Ingreso" if t == "Ingreso" else "🔴 Gasto")
        col_tbl, col_dl = st.columns([5, 1])
        with col_tbl:
            st.dataframe(disp.rename(columns={
                "fecha": "Fecha", "banco": "Banco", "descripcion": "Descripción",
                "categoria": "Categoría", "tipo": "Tipo", "monto": "Monto"
            }), hide_index=True, use_container_width=True, height=400)
        with col_dl:
            st.markdown("<br><br>", unsafe_allow_html=True)
            download_csv(
                dm_sel[["fecha","banco","descripcion","categoria","tipo","monto"]].assign(
                    fecha=lambda d: d["fecha"].dt.strftime("%Y-%m-%d")
                ),
                f"dashboard_{sel_month}.csv"
            )
