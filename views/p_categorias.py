"""Página: Gestión de reglas de categorización y corrección de transacciones."""
from datetime import datetime

import streamlit as st

from utils.config import CATEGORIES, CATEGORY_RULES
from utils.loaders import load_reglas_categorias
from utils.sheets import _append_row, _write_tab, _new_id, _read_transacciones_raw, _update_transaction_category


def render():
    st.title("🏷️ Categorías & Reglas")

    tab_reglas, tab_agregar, tab_corregir = st.tabs(
        ["📋 Reglas activas", "➕ Agregar regla", "✏️ Corregir transacciones"]
    )

    # ── Tab 1: Ver reglas ─────────────────────────────────────────────────────
    with tab_reglas:
        st.subheader("Reglas incorporadas (del sistema)")
        st.caption("Estas reglas siempre están activas. Las reglas personalizadas tienen mayor prioridad.")

        rows_built = []
        for cat, keywords in CATEGORY_RULES.items():
            for kw in keywords:
                rows_built.append({"Palabra clave": kw, "Categoría": cat, "Origen": "Sistema"})

        st.dataframe(rows_built, use_container_width=True, height=300)

        st.subheader("Reglas personalizadas (tuyas)")
        df_reglas = load_reglas_categorias()

        if df_reglas.empty:
            st.info("No tienes reglas personalizadas aún. Agrégalas en la pestaña ➕.")
        else:
            for _, row in df_reglas.iterrows():
                rc1, rc2, rc3 = st.columns([3, 3, 1])
                rc1.write(f"**{row['palabra_clave']}**")
                rc2.write(row["categoria"])
                if rc3.button("🗑️", key=f"del_reg_{row['id']}", help="Eliminar regla"):
                    df_all = load_reglas_categorias()
                    _write_tab("Reglas_Categorias", df_all[df_all["id"] != row["id"]])
                    st.cache_data.clear()
                    st.rerun()

    # ── Tab 2: Agregar regla ──────────────────────────────────────────────────
    with tab_agregar:
        st.subheader("Nueva regla de categorización")
        st.caption(
            "Si la descripción de una transacción contiene la palabra clave, "
            "se asignará la categoría indicada. Esta regla también se usará al importar cartolas."
        )

        with st.form("form_regla", clear_on_submit=True):
            r1, r2 = st.columns(2)
            palabra_clave = r1.text_input("Palabra clave *",
                                           placeholder='Ej: "supermercado", "copec", "uber"')
            categoria     = r2.selectbox("Categoría *", CATEGORIES)
            st.caption("La búsqueda es insensible a mayúsculas/minúsculas.")

            if st.form_submit_button("💾 Guardar regla", type="primary"):
                if not palabra_clave:
                    st.error("La palabra clave es obligatoria.")
                else:
                    _append_row("Reglas_Categorias", [
                        _new_id(),
                        palabra_clave.strip().lower(),
                        categoria,
                        datetime.now().isoformat()
                    ])
                    st.success(f"✅ Regla guardada: **{palabra_clave}** → {categoria}")
                    st.cache_data.clear()

        # Importar regla desde corrección rápida
        st.markdown("---")
        st.subheader("Prueba una regla")
        test_desc = st.text_input("Descripción de prueba",
                                   placeholder="Pega aquí una descripción de transacción")
        if test_desc:
            from utils.categorias import categorize
            df_reglas = load_reglas_categorias()
            custom = df_reglas.to_dict("records") if not df_reglas.empty else []
            result = categorize(test_desc, custom)
            color  = "#2ecc71" if result != "Otros" else "#e74c3c"
            st.markdown(
                f'<div style="background:#1a1a2e;border-radius:8px;padding:12px;'
                f'border-left:4px solid {color}">'
                f'Categoría detectada: <b style="color:{color}">{result}</b></div>',
                unsafe_allow_html=True
            )

    # ── Tab 3: Corregir transacciones ─────────────────────────────────────────
    with tab_corregir:
        st.subheader("Corregir categorías en Transacciones")
        st.caption(
            "Corrige transacciones mal categorizadas. "
            "Los cambios se guardan directamente en Google Sheets."
        )

        filtro = st.selectbox(
            "Ver transacciones",
            ["Solo 'Otros' (sin categoría)", "Todas las transacciones"],
        )
        search = st.text_input("Buscar descripción", placeholder="Filtra por texto...")

        try:
            header, indexed_rows = _read_transacciones_raw()
        except Exception as e:
            st.error(f"No se pudo leer Transacciones: {e}")
            return

        if not indexed_rows:
            st.info("No hay transacciones en el sheet.")
            return

        # Columnas: fecha, banco, cuenta, moneda, tipo, descripcion, categoria, monto
        col_map = {name: i for i, name in enumerate(header)}

        def get_col(row, name, default=""):
            idx = col_map.get(name, -1)
            return row[idx] if 0 <= idx < len(row) else default

        filtered = []
        for sheet_row, row in indexed_rows:
            cat  = get_col(row, "Categoría") or get_col(row, "categoria")
            desc = get_col(row, "Descripción") or get_col(row, "descripcion")
            if filtro == "Solo 'Otros' (sin categoría)" and cat not in ("Otros", ""):
                continue
            if search and search.lower() not in desc.lower():
                continue
            filtered.append((sheet_row, row, cat, desc))

        if not filtered:
            st.info("No hay transacciones con ese filtro.")
            return

        st.caption(f"{len(filtered)} transacciones encontradas.")

        for sheet_row, row, cat, desc in filtered[:50]:  # max 50 para no saturar la UI
            fecha = get_col(row, "Fecha") or get_col(row, "fecha")
            monto = get_col(row, "Monto") or get_col(row, "monto")
            tipo  = get_col(row, "Tipo") or get_col(row, "tipo")

            c1, c2, c3, c4, c5 = st.columns([1.5, 3.5, 1.5, 2.5, 1.2])
            c1.write(fecha)
            c2.write(desc[:55])
            icon = "🟢" if tipo == "Ingreso" else "🔴"
            c3.write(f"{icon} {monto}")

            cat_idx = CATEGORIES.index(cat) if cat in CATEGORIES else len(CATEGORIES) - 1
            new_cat = c4.selectbox(
                "", CATEGORIES, index=cat_idx,
                key=f"corr_cat_{sheet_row}",
                label_visibility="collapsed"
            )

            if c5.button("Guardar", key=f"corr_save_{sheet_row}"):
                if new_cat != cat:
                    try:
                        _update_transaction_category(sheet_row, new_cat)
                        st.cache_data.clear()
                        st.success(f"✅ Categoría actualizada → **{new_cat}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.info("Sin cambios.")

        if len(filtered) > 50:
            st.caption(f"Mostrando 50 de {len(filtered)}. Usa el filtro para acotar la búsqueda.")
