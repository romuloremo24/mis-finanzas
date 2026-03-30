"""Página: Registro y gestión de gastos manuales."""
from datetime import date

import plotly.express as px
import streamlit as st

from utils.config import CATEGORIES, PAYMENT_METHODS
from utils.loaders import load_gastos_manuales
from utils.sheets import _append_row, _write_tab, _new_id
from utils.ui import fmt_clp, fmt_amount, apply_layout, download_csv


def render():
    st.title("✏️ Gastos Manuales")
    st.caption("Registra gastos en efectivo o cualquier gasto que no aparezca en tus cartolas.")

    tab_new, tab_list, tab_stats = st.tabs(["➕ Nuevo gasto", "📋 Historial", "📊 Estadísticas"])

    # ── Formulario nuevo gasto ────────────────────────────────────────────────
    with tab_new:
        # Autocompletado de comercios frecuentes
        df_all = load_gastos_manuales()
        comercios_frecuentes = []
        if not df_all.empty:
            comercios_frecuentes = df_all["descripcion"].value_counts().head(10).index.tolist()

        with st.form("form_gasto", clear_on_submit=True):
            c1, c2 = st.columns(2)
            fecha   = c1.date_input("Fecha", value=date.today())
            monto   = c2.number_input("Monto *", min_value=0.0, step=500.0, format="%.0f")

            if comercios_frecuentes:
                st.caption("Comercios frecuentes: " + " · ".join(f"`{c}`" for c in comercios_frecuentes[:5]))
            descripcion = st.text_input("Descripción *", placeholder="Ej: Almuerzo con clientes")

            c3, c4, c5 = st.columns(3)
            moneda      = c3.selectbox("Moneda", ["CLP", "USD"])
            categoria   = c4.selectbox("Categoría", CATEGORIES)
            metodo_pago = c5.selectbox("Método de pago", PAYMENT_METHODS)

            notas     = st.text_area("Notas", height=80, placeholder="Opcional")
            recurrente = st.checkbox("Marcar como gasto recurrente mensual")

            submitted = st.form_submit_button("💾 Guardar gasto", type="primary", use_container_width=True)

        if submitted:
            if not descripcion:
                st.error("La descripción es obligatoria.")
            elif monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                notas_final = notas or ""
                if recurrente:
                    notas_final = (notas_final + " [RECURRENTE]").strip()
                _append_row("Gastos_Manuales", [
                    _new_id(), fecha.isoformat(), descripcion, monto,
                    moneda, categoria, metodo_pago, notas_final
                ])
                st.success(f"✅ Guardado: **{descripcion}** — {fmt_amount(monto, moneda)}")
                st.cache_data.clear()

    # ── Historial ─────────────────────────────────────────────────────────────
    with tab_list:
        df = load_gastos_manuales()
        if df.empty:
            st.info("No hay gastos manuales registrados aún.")
        else:
            hf1, hf2, hf3 = st.columns([2, 2, 1])
            all_m  = ["Todos"] + sorted(df["mes"].dropna().unique(), reverse=True)
            sel_m  = hf1.selectbox("Mes", all_m, key="gm_mes")
            all_c  = ["Todas"] + sorted(df["categoria"].dropna().unique())
            sel_c  = hf2.selectbox("Categoría", all_c, key="gm_cat")
            search = hf3.text_input("Buscar", key="gm_search")

            filt = df.copy()
            if sel_m != "Todos":
                filt = filt[filt["mes"] == sel_m]
            if sel_c != "Todas":
                filt = filt[filt["categoria"] == sel_c]
            if search:
                filt = filt[filt["descripcion"].str.contains(search, case=False, na=False)]

            total = filt["monto"].sum()
            col_info, col_dl = st.columns([4, 1])
            col_info.markdown(f"**{len(filt)} registros** — Total: **{fmt_clp(total)}**")
            export = filt[["fecha","descripcion","categoria","metodo_pago","monto","moneda","notas"]].copy()
            export["fecha"] = export["fecha"].dt.strftime("%Y-%m-%d")
            with col_dl:
                download_csv(export, "gastos_manuales.csv")

            for _, row in filt.iterrows():
                with st.container():
                    rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([1.5, 3, 2, 2, 1.5, 0.5])
                    rc1.write(row["fecha"].strftime("%d/%m/%Y") if hasattr(row["fecha"], "strftime") else "—")
                    rc2.write(row["descripcion"])
                    rc3.write(row["categoria"])
                    rc4.write(row["metodo_pago"])
                    rc5.write(fmt_amount(row["monto"], row["moneda"]))
                    if rc6.button("🗑️", key=f"del_gm_{row['id']}", help="Eliminar"):
                        df_all_write = load_gastos_manuales()
                        _write_tab("Gastos_Manuales",
                                   df_all_write[df_all_write["id"] != row["id"]].drop(columns=["mes"], errors="ignore"))
                        st.cache_data.clear()
                        st.rerun()

    # ── Estadísticas ──────────────────────────────────────────────────────────
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
