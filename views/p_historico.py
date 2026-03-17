"""Página: Histórico comparativo multi-mes."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.config import C_GREEN, C_RED, C_PURPLE
from utils.loaders import load_transactions, load_gastos_manuales
from utils.ui import fmt_clp, apply_layout, download_csv


def render():
    st.title("📈 Histórico Comparativo")

    df = load_transactions()
    if df.empty:
        st.warning("Sin datos.")
        return

    df_clp = df[df["moneda"] == "CLP"]
    df_man = load_gastos_manuales()

    # ── Construir resumen mensual ──────────────────────────────────────────────
    ing     = df_clp[~df_clp["es_gasto"]].groupby("mes")["monto"].sum().rename("Ingresos")
    gst     = df_clp[df_clp["es_gasto"]].groupby("mes")["monto"].sum().rename("Gastos")
    monthly = pd.concat([ing, gst], axis=1).fillna(0).reset_index().sort_values("mes")

    if not df_man.empty:
        man_m   = df_man.groupby("mes")["monto"].sum().rename("GastosManual")
        monthly = monthly.join(man_m, on="mes", how="left").fillna(0)
        monthly["Gastos"] += monthly["GastosManual"]

    monthly["Balance"] = monthly["Ingresos"] - monthly["Gastos"]
    monthly["Ahorro%"] = (monthly["Balance"] / monthly["Ingresos"].replace(0, 1) * 100).round(1)

    if monthly.empty:
        st.info("No hay datos suficientes.")
        return

    # ── Selector de rango ─────────────────────────────────────────────────────
    all_months = sorted(monthly["mes"].unique())
    start_m = all_months[0]
    end_m   = all_months[-1]
    if len(all_months) > 1:
        rf1, rf2 = st.columns(2)
        start_m = rf1.selectbox("Desde", all_months, index=0)
        end_m   = rf2.selectbox("Hasta", all_months, index=len(all_months) - 1)
        monthly = monthly[(monthly["mes"] >= start_m) & (monthly["mes"] <= end_m)]

    # ── Gráfico 1 & 2: Ingresos/Gastos y Balance ─────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ingresos vs Gastos")
        fig = go.Figure()
        fig.add_bar(name="Ingresos", x=monthly["mes"], y=monthly["Ingresos"],
                    marker_color=C_GREEN,
                    text=monthly["Ingresos"].apply(lambda v: f"${v/1e6:.1f}M"),
                    textposition="outside")
        fig.add_bar(name="Gastos", x=monthly["mes"], y=monthly["Gastos"],
                    marker_color=C_RED,
                    text=monthly["Gastos"].apply(lambda v: f"${v/1e6:.1f}M"),
                    textposition="outside")
        apply_layout(fig, barmode="group", height=340, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Balance mensual")
        colors = [C_GREEN if v >= 0 else C_RED for v in monthly["Balance"]]
        fig = go.Figure(go.Bar(
            x=monthly["mes"], y=monthly["Balance"], marker_color=colors,
            text=monthly["Balance"].apply(lambda v: f"${v/1e6:.1f}M"),
            textposition="outside"
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#555")
        apply_layout(fig, height=340, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

    # ── Gráfico 3 & 4: Ahorro% y categorías ─────────────────────────────────
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Tasa de ahorro %")
        fig = go.Figure()
        fig.add_scatter(
            x=monthly["mes"], y=monthly["Ahorro%"],
            mode="lines+markers+text",
            line=dict(color=C_PURPLE, width=2),
            marker=dict(size=8, color=C_PURPLE),
            text=monthly["Ahorro%"].apply(lambda v: f"{v:.0f}%"),
            textposition="top center"
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#555")
        apply_layout(fig, height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.subheader("Gastos por categoría (stacked)")
        cat_m = df_clp[df_clp["es_gasto"]].copy()
        if not df_man.empty:
            man_cat = df_man[["mes", "categoria", "monto"]].copy()
            cat_m   = pd.concat([cat_m[["mes", "categoria", "monto"]], man_cat], ignore_index=True)
        cat_m = cat_m.groupby(["mes", "categoria"])["monto"].sum().reset_index()
        if not cat_m.empty:
            cat_m = cat_m[(cat_m["mes"] >= start_m) & (cat_m["mes"] <= end_m)]
            fig = px.bar(cat_m, x="mes", y="monto", color="categoria",
                         barmode="stack",
                         labels={"monto": "CLP", "mes": "Mes", "categoria": "Categoría"},
                         color_discrete_sequence=px.colors.qualitative.Set2)
            apply_layout(fig, height=340, yaxis_tickformat="$,.0f",
                         legend=dict(orientation="v", x=1.02, y=0.5,
                                     bgcolor="rgba(0,0,0,0)", font_color="#ccc"))
            st.plotly_chart(fig, use_container_width=True)

    # ── Heatmap ───────────────────────────────────────────────────────────────
    st.subheader("Mapa de calor — Gasto por categoría")
    cat_pivot = df_clp[df_clp["es_gasto"]].groupby(["mes", "categoria"])["monto"].sum()
    if not cat_pivot.empty:
        heat = cat_pivot.unstack(fill_value=0)
        fig  = px.imshow(
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

    # ── Tabla resumen + exportación ───────────────────────────────────────────
    st.subheader("Tabla resumen")
    tbl_raw = monthly[["mes", "Ingresos", "Gastos", "Balance", "Ahorro%"]].copy()

    col_tbl, col_dl = st.columns([5, 1])
    with col_tbl:
        tbl = tbl_raw.copy()
        tbl["Ingresos"] = tbl["Ingresos"].apply(fmt_clp)
        tbl["Gastos"]   = tbl["Gastos"].apply(fmt_clp)
        tbl["Balance"]  = tbl["Balance"].apply(fmt_clp)
        tbl["Ahorro%"]  = tbl["Ahorro%"].apply(lambda v: f"{v:.1f}%")
        st.dataframe(tbl.rename(columns={"mes": "Mes"}),
                     hide_index=True, use_container_width=True)
    with col_dl:
        st.markdown("<br><br>", unsafe_allow_html=True)
        download_csv(tbl_raw.rename(columns={"mes": "Mes"}), "historico.csv")


