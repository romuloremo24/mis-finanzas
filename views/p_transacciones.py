"""Página: Vista y filtrado de todas las transacciones importadas."""
import streamlit as st

from utils.loaders import load_transactions
from utils.ui import fmt_clp, fmt_usd, apply_layout, download_csv


def render():
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
        search    = f5.text_input("Buscar descripción")

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
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Transacciones", len(filt))
    mc2.metric("Total gastos CLP",   fmt_clp(g_tot))
    mc3.metric("Total ingresos CLP", fmt_clp(i_tot))
    mc4.metric("Balance CLP", fmt_clp(i_tot - g_tot))

    # ── Tabla + exportación ───────────────────────────────────────────────────
    disp = filt.sort_values("fecha", ascending=False).copy()
    disp["fecha"] = disp["fecha"].dt.strftime("%d/%m/%Y")
    disp["monto_fmt"] = disp.apply(
        lambda r: (fmt_clp if r["moneda"] == "CLP" else fmt_usd)(r["monto"]), axis=1
    )
    disp["tipo"] = disp["tipo"].apply(lambda t: "🟢 Ingreso" if t == "Ingreso" else "🔴 Gasto")

    col_tbl, col_dl = st.columns([6, 1])
    with col_tbl:
        st.dataframe(
            disp[["fecha", "banco", "cuenta", "descripcion", "categoria",
                  "tipo", "monto_fmt", "moneda"]].rename(columns={
                "fecha": "Fecha", "banco": "Banco", "cuenta": "Cuenta",
                "descripcion": "Descripción", "categoria": "Categoría",
                "tipo": "Tipo", "monto_fmt": "Monto", "moneda": "Moneda"
            }),
            hide_index=True, use_container_width=True, height=550,
        )
    with col_dl:
        st.markdown("<br><br>", unsafe_allow_html=True)
        export = filt[["fecha","banco","cuenta","descripcion","categoria","tipo","monto","moneda"]].copy()
        export["fecha"] = export["fecha"].dt.strftime("%Y-%m-%d")
        download_csv(export, "transacciones.csv")
