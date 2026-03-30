"""Pagina: Documentos cargados — registro y cobertura de cartolas importadas."""
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.config import C_GREEN, C_RED, C_BLUE, C_GOLD, C_PURPLE, C_TEAL, C_CARD, C_BORDER, ACCOUNT_TYPES
from utils.loaders import load_documentos, load_transactions
from utils.sheets import _write_tab, _append_row, _new_id
from utils.ui import fmt_clp, kpi_card, apply_layout, download_csv


def _tipo_cuenta(cuenta: str) -> str:
    return ACCOUNT_TYPES.get(cuenta, cuenta)


def render():
    st.title("📋 Documentos Cargados")
    st.caption("Registro de todas las cartolas importadas: periodo, banco, tipo de cuenta y estado.")

    docs = load_documentos()
    df_tx = load_transactions()

    # ── KPIs resumen ──────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    n_docs = len(docs)
    n_banks = docs["banco"].nunique() if not docs.empty else 0
    n_periods = docs["periodo"].nunique() if not docs.empty else 0
    total_tx = int(docs["num_transacciones"].sum()) if not docs.empty else 0
    tipos = docs["tipo_cuenta"].nunique() if not docs.empty else 0

    kpi_card(c1, "Documentos", str(n_docs), "", C_BLUE, "📄")
    kpi_card(c2, "Bancos", str(n_banks), "", C_PURPLE, "🏦")
    kpi_card(c3, "Periodos", str(n_periods), "", C_GOLD, "📅")
    kpi_card(c4, "Transacciones", f"{total_tx:,}", "", C_GREEN, "📝")
    kpi_card(c5, "Tipos Cuenta", str(tipos), "", C_TEAL, "💳")

    st.markdown("<br>", unsafe_allow_html=True)

    if docs.empty:
        st.info("No hay documentos registrados. Importa cartolas desde **📂 Importar Cartola** para comenzar a trackear.")
        _render_coverage_from_transactions(df_tx)
        return

    # ── Filtros ───────────────────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        all_banks = ["(Todos)"] + sorted(docs["banco"].dropna().unique().tolist())
        sel_bank = f1.selectbox("Banco", all_banks, key="doc_bank")

        all_tipos = ["(Todos)"] + sorted(docs["tipo_cuenta"].dropna().unique().tolist())
        sel_tipo = f2.selectbox("Tipo cuenta", all_tipos, key="doc_tipo")

        all_periods = ["(Todos)"] + sorted(docs["periodo"].dropna().unique().tolist(), reverse=True)
        sel_period = f3.selectbox("Periodo", all_periods, key="doc_period")

        all_status = ["(Todos)"] + sorted(docs["estado"].dropna().unique().tolist())
        sel_status = f4.selectbox("Estado", all_status, key="doc_status")

    filt = docs.copy()
    if sel_bank != "(Todos)":
        filt = filt[filt["banco"] == sel_bank]
    if sel_tipo != "(Todos)":
        filt = filt[filt["tipo_cuenta"] == sel_tipo]
    if sel_period != "(Todos)":
        filt = filt[filt["periodo"] == sel_period]
    if sel_status != "(Todos)":
        filt = filt[filt["estado"] == sel_status]

    # ── Tabla principal ───────────────────────────────────────────────────────
    st.subheader("Listado de documentos")

    disp = filt.copy()
    disp["fecha_importacion_fmt"] = disp["fecha_importacion"].dt.strftime("%d/%m/%Y %H:%M")
    disp["fecha_desde_fmt"] = disp["fecha_desde"].dt.strftime("%d/%m/%Y")
    disp["fecha_hasta_fmt"] = disp["fecha_hasta"].dt.strftime("%d/%m/%Y")
    disp["rango"] = disp["fecha_desde_fmt"].fillna("") + " → " + disp["fecha_hasta_fmt"].fillna("")
    disp["gastos_fmt"] = disp["total_gastos"].apply(fmt_clp)
    disp["ingresos_fmt"] = disp["total_ingresos"].apply(fmt_clp)
    disp["n_tx"] = disp["num_transacciones"].astype(int)

    # Estado con iconos
    status_map = {"nuevo": "🟢 Nuevo", "antiguo": "🟠 Antiguo", "reimportado": "🔵 Reimportado"}
    disp["estado_fmt"] = disp["estado"].map(status_map).fillna(disp["estado"])

    show_cols = {
        "periodo": "Periodo",
        "banco": "Banco",
        "cuenta": "Cuenta",
        "tipo_cuenta": "Tipo",
        "moneda": "Moneda",
        "rango": "Rango fechas",
        "n_tx": "# Tx",
        "gastos_fmt": "Gastos",
        "ingresos_fmt": "Ingresos",
        "estado_fmt": "Estado",
        "fecha_importacion_fmt": "Importado",
        "nombre_archivo": "Archivo",
    }
    col_tbl, col_dl = st.columns([6, 1])
    with col_tbl:
        st.dataframe(
            disp[list(show_cols.keys())].rename(columns=show_cols),
            hide_index=True, use_container_width=True, height=400,
        )
    with col_dl:
        st.markdown("<br><br>", unsafe_allow_html=True)
        download_csv(
            filt[["periodo", "banco", "cuenta", "tipo_cuenta", "moneda",
                  "fecha_desde", "fecha_hasta", "num_transacciones",
                  "total_gastos", "total_ingresos", "estado", "fecha_importacion", "nombre_archivo"]],
            "documentos_cargados.csv"
        )

    # ── Timeline de cobertura ─────────────────────────────────────────────────
    st.subheader("📅 Cobertura temporal")

    timeline = filt.dropna(subset=["fecha_desde", "fecha_hasta"]).copy()
    if not timeline.empty:
        timeline["label"] = timeline["banco"] + " — " + timeline["cuenta"]
        fig = go.Figure()
        colors_bank = {b: c for b, c in zip(
            timeline["banco"].unique(),
            [C_BLUE, C_GREEN, C_PURPLE, C_GOLD, C_RED, C_TEAL]
        )}
        for _, row in timeline.iterrows():
            fig.add_trace(go.Bar(
                x=[(row["fecha_hasta"] - row["fecha_desde"]).days],
                y=[row["label"]],
                base=row["fecha_desde"],
                orientation="h",
                marker_color=colors_bank.get(row["banco"], C_BLUE),
                text=row["periodo"],
                textposition="inside",
                hovertemplate=f"{row['banco']} {row['cuenta']}<br>"
                              f"{row['fecha_desde'].strftime('%d/%m/%Y')} → {row['fecha_hasta'].strftime('%d/%m/%Y')}<br>"
                              f"{int(row['num_transacciones'])} transacciones<extra></extra>",
                showlegend=False,
            ))
        apply_layout(fig, height=max(200, len(timeline) * 40 + 60),
                     xaxis_type="date", barmode="stack",
                     yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de rango de fechas para mostrar la timeline.")

    # ── Resumen por banco y tipo ──────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Documentos por banco")
        by_bank = filt.groupby("banco").agg(
            docs=("id", "count"),
            tx=("num_transacciones", "sum"),
            gastos=("total_gastos", "sum"),
        ).reset_index().sort_values("gastos", ascending=False)
        if not by_bank.empty:
            fig = px.bar(by_bank, x="banco", y="docs", color="banco",
                         text="docs",
                         color_discrete_sequence=px.colors.qualitative.Set2)
            apply_layout(fig, height=300, showlegend=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Documentos por tipo de cuenta")
        by_tipo = filt.groupby("tipo_cuenta")["id"].count().reset_index()
        by_tipo.columns = ["Tipo", "Cantidad"]
        if not by_tipo.empty:
            fig = px.pie(by_tipo, values="Cantidad", names="Tipo",
                         hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
            apply_layout(fig, height=300,
                         legend=dict(orientation="h", y=-0.15, bgcolor="rgba(0,0,0,0)", font_color="#ccc"))
            fig.update_traces(textfont_color="#fff", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

    # ── Deteccion de brechas ──────────────────────────────────────────────────
    _render_gaps(filt)

    # ── Estadisticas por periodo ──────────────────────────────────────────────
    st.subheader("📊 Gastos e ingresos por periodo importado")
    by_period = filt.groupby("periodo").agg(
        gastos=("total_gastos", "sum"),
        ingresos=("total_ingresos", "sum"),
    ).reset_index().sort_values("periodo")
    if not by_period.empty:
        fig = go.Figure()
        fig.add_bar(name="Ingresos", x=by_period["periodo"], y=by_period["ingresos"],
                    marker_color=C_GREEN)
        fig.add_bar(name="Gastos", x=by_period["periodo"], y=by_period["gastos"],
                    marker_color=C_RED)
        apply_layout(fig, barmode="group", height=320, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)


def _render_gaps(docs: pd.DataFrame):
    if docs.empty:
        return

    st.subheader("⚠️ Brechas de cobertura")
    gaps = []
    for combo, grp in docs.groupby(["banco", "cuenta"]):
        banco, cuenta = combo
        periods = sorted(grp["periodo"].dropna().unique())
        if len(periods) < 2:
            continue
        for i in range(len(periods) - 1):
            curr = periods[i]
            nxt = periods[i + 1]
            try:
                curr_date = pd.Timestamp(curr + "-01")
                nxt_date = pd.Timestamp(nxt + "-01")
                diff_months = (nxt_date.year - curr_date.year) * 12 + nxt_date.month - curr_date.month
                if diff_months > 1:
                    missing = []
                    d = curr_date + pd.DateOffset(months=1)
                    while d < nxt_date:
                        missing.append(d.strftime("%Y-%m"))
                        d += pd.DateOffset(months=1)
                    gaps.append({
                        "banco": banco,
                        "cuenta": cuenta,
                        "meses_faltantes": ", ".join(missing),
                        "cantidad": len(missing),
                    })
            except Exception:
                pass

    if gaps:
        gap_df = pd.DataFrame(gaps)
        st.warning(f"Se detectaron **{len(gaps)}** brechas en la cobertura de cartolas:")
        st.dataframe(
            gap_df.rename(columns={
                "banco": "Banco", "cuenta": "Cuenta",
                "meses_faltantes": "Meses faltantes", "cantidad": "# Meses"
            }),
            hide_index=True, use_container_width=True,
        )
    else:
        st.success("Sin brechas detectadas en la cobertura de periodos.")


def _render_coverage_from_transactions(df_tx: pd.DataFrame):
    if df_tx.empty:
        return
    st.subheader("📊 Cobertura derivada de transacciones existentes")
    st.caption("Estos datos se calculan de las transacciones ya importadas (sin registro formal de documento).")

    coverage = df_tx.groupby(["banco", "cuenta", "mes"]).agg(
        n_tx=("descripcion", "count"),
        gastos=("monto", lambda x: x[df_tx.loc[x.index, "es_gasto"]].sum()),
        ingresos=("monto", lambda x: x[~df_tx.loc[x.index, "es_gasto"]].sum()),
    ).reset_index().sort_values(["mes", "banco", "cuenta"], ascending=[False, True, True])

    if not coverage.empty:
        coverage["tipo_cuenta"] = coverage["cuenta"].map(ACCOUNT_TYPES).fillna(coverage["cuenta"])
        disp = coverage.rename(columns={
            "mes": "Periodo", "banco": "Banco", "cuenta": "Cuenta",
            "tipo_cuenta": "Tipo", "n_tx": "# Tx",
            "gastos": "Gastos", "ingresos": "Ingresos",
        })
        disp["Gastos"] = disp["Gastos"].apply(fmt_clp)
        disp["Ingresos"] = disp["Ingresos"].apply(fmt_clp)
        st.dataframe(disp, hide_index=True, use_container_width=True)
