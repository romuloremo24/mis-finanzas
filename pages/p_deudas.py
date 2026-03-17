"""Página: Deudas, préstamos e ingresos esperados."""
from datetime import date, datetime

import pandas as pd
import streamlit as st

from utils.config import C_GREEN, C_RED, C_CARD
from utils.loaders import load_deudas, load_ingresos_esperados
from utils.sheets import _append_row, _write_tab, _new_id
from utils.ui import fmt_clp, fmt_amount, kpi_card


def _render_debt_section(df_d, tipo_key: str):
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
        f'<span style="color:#888;font-size:13px;margin-left:12px">{len(pending)} registros</span></div>',
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


def render():
    st.title("💳 Deudas & Pendientes")

    df_deu = load_deudas()

    if not df_deu.empty:
        pend     = df_deu[df_deu["estado"] == "pendiente"]
        me_deben = pend[pend["tipo"] == "me_deben"]["monto"].sum() if not pend.empty else 0
        debo     = pend[pend["tipo"] == "debo"]["monto"].sum()     if not pend.empty else 0
        neto     = me_deben - debo
        sc1, sc2, sc3 = st.columns(3)
        kpi_card(sc1, "Me deben", fmt_clp(me_deben), "", C_GREEN, "💰")
        kpi_card(sc2, "Debo",     fmt_clp(debo),     "", C_RED,   "📤")
        kpi_card(sc3, "Neto",     fmt_clp(neto),     "",
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
                ie_moneda     = ie3.selectbox("Moneda", ["CLP", "USD"], key="ie_mon")
                ie_fecha      = ie4.date_input("Fecha esperada", key="ie_fecha")
                ie_recurrente = ie5.checkbox("Mensual recurrente")
                ie_notas      = st.text_area("Notas", height=70, key="ie_notas")

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

    _empty = pd.DataFrame()

    with tab_me_deben:
        st.subheader("💰 Dinero que me deben")
        _render_debt_section(
            df_deu[df_deu["tipo"] == "me_deben"] if not df_deu.empty else _empty,
            "me_deben"
        )

    with tab_debo:
        st.subheader("📤 Dinero que le debo a otros")
        _render_debt_section(
            df_deu[df_deu["tipo"] == "debo"] if not df_deu.empty else _empty,
            "debo"
        )

    with tab_esperados:
        st.subheader("🔜 Ingresos esperados / por recibir")
        df_ie = load_ingresos_esperados()
        if df_ie.empty:
            st.info("No hay ingresos esperados registrados.")
        else:
            pend_ie  = df_ie[df_ie["estado"] == "pendiente"]
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
