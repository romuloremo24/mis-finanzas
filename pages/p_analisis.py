"""Página: Análisis detallado del mes + comparación con presupuesto."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.config import C_RED
from utils.loaders import load_transactions
from utils.ui import fmt_clp, apply_layout, download_csv


def render():
    st.title("🤖 Análisis & Presupuesto")

    df = load_transactions()
    if df.empty:
        st.warning("Sin datos de transacciones.")
        return

    all_months = sorted(df["mes"].dropna().unique(), reverse=True)
    sel_month  = st.selectbox("Mes a analizar", all_months)

    dm      = df[df["mes"] == sel_month]
    df_clp  = dm[dm["moneda"] == "CLP"]
    gastos  = df_clp[df_clp["es_gasto"]]
    ingresos = df_clp[~df_clp["es_gasto"]]

    total_g = gastos["monto"].sum()
    total_i = ingresos["monto"].sum()
    by_cat  = gastos.groupby("categoria")["monto"].sum().sort_values(ascending=False)

    # ── Contexto financiero ───────────────────────────────────────────────────
    context = f"""Período: {sel_month}
Total ingresos CLP: ${total_i:,.0f}
Total gastos CLP: ${total_g:,.0f}
Balance: ${total_i - total_g:,.0f}
Tasa de ahorro: {(total_i - total_g) / total_i * 100:.1f}% {"" if total_i == 0 else ""}

Gastos por categoría:
{chr(10).join(f"  {c}: ${v:,.0f} ({v/total_g*100:.1f}%)" for c, v in by_cat.items() if total_g > 0)}

Top 10 gastos individuales:
{chr(10).join(f"  {r['descripcion'][:50]}: ${r['monto']:,.0f}" for _, r in gastos.nlargest(10, 'monto').iterrows())}
"""
    with st.expander("📋 Contexto financiero del mes", expanded=False):
        st.text_area("", context, height=250, label_visibility="collapsed")
        download_csv(
            gastos[["fecha","descripcion","categoria","monto"]].assign(
                fecha=lambda d: d["fecha"].dt.strftime("%Y-%m-%d")
            ),
            f"analisis_{sel_month}.csv",
            label="⬇️ Exportar gastos del mes"
        )

    # ── Charts ────────────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Top categorías")
        if not by_cat.empty:
            fig = go.Figure(go.Bar(
                x=by_cat.values, y=by_cat.index, orientation="h",
                marker=dict(color=by_cat.values, colorscale="Oranges", showscale=False),
                text=[f"{v/total_g*100:.0f}%" for v in by_cat.values] if total_g > 0 else [],
                textposition="outside",
            ))
            apply_layout(fig, height=320, xaxis_tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Evolución diaria de gastos")
        daily = gastos.groupby(gastos["fecha"].dt.date)["monto"].sum().reset_index()
        daily.columns = ["fecha", "monto"]
        if not daily.empty:
            avg   = daily["monto"].mean()
            fig   = px.area(daily, x="fecha", y="monto", color_discrete_sequence=[C_RED])
            fig.add_hline(y=avg, line_dash="dot", line_color="#f39c12",
                          annotation_text=f"Promedio ${avg:,.0f}")
            apply_layout(fig, height=320, yaxis_tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

    # ── Top comercios ─────────────────────────────────────────────────────────
    st.subheader("🏪 Top 10 comercios")
    top_comercios = (gastos.groupby("descripcion")["monto"]
                     .agg(["sum", "count"])
                     .sort_values("sum", ascending=False)
                     .head(10)
                     .reset_index())
    top_comercios.columns = ["Descripción", "Total", "Veces"]
    top_comercios["Total"] = top_comercios["Total"].apply(fmt_clp)
    st.dataframe(top_comercios, hide_index=True, use_container_width=True)

    # ── Presupuesto ───────────────────────────────────────────────────────────
    st.subheader("🎯 Comparar con presupuesto")
    st.caption("Define tu presupuesto mensual por categoría y mira cuánto te queda.")

    budget_cats = ["Supermercado", "Restaurante", "Combustible", "Entretención",
                   "Ropa/Calzado", "Salud", "Transporte", "Servicios"]

    budget_cols = st.columns(4)
    budgets = {}
    for idx, cat in enumerate(budget_cats):
        gastado     = by_cat.get(cat, 0)
        budgets[cat] = budget_cols[idx % 4].number_input(
            f"{cat}", value=int(gastado * 1.2) or 50000, step=10000, format="%d", key=f"bud_{cat}"
        )

    st.markdown("#### Progreso vs presupuesto")
    prog_cols = st.columns(4)
    for idx, cat in enumerate(budget_cats):
        gastado     = by_cat.get(cat, 0)
        presupuesto = budgets[cat]
        pct         = (gastado / presupuesto * 100) if presupuesto > 0 else 0
        color       = "🟢" if pct < 80 else "🟡" if pct < 100 else "🔴"
        with prog_cols[idx % 4]:
            st.caption(f"{color} **{cat}**")
            st.progress(min(pct / 100, 1.0))
            st.caption(f"{fmt_clp(gastado)} / {fmt_clp(presupuesto)} ({pct:.0f}%)")
