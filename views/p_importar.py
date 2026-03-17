"""Página: Importación de cartolas bancarias desde CSV o Excel."""
from datetime import datetime
import io

import pandas as pd
import streamlit as st

from utils.categorias import categorize, parse_clp_amount
from utils.config import CATEGORIES
from utils.loaders import load_transactions, load_reglas_categorias
from utils.sheets import _append_rows, _new_id

# ── Presets de bancos (columnas del CSV de descarga web) ──────────────────────
BANK_PRESETS = {
    "BCI / Lider BCI": {
        "sep": ";",
        "date_col": "Fecha",
        "desc_col": "Descripción",
        "cargo_col": "Cargo",
        "abono_col": "Abono",
        "date_fmt": "%d/%m/%Y",
        "banco": "BCI",
        "cuenta": "Cuenta Vista",
        "moneda": "CLP",
    },
    "Santander Cuenta Corriente": {
        "sep": ";",
        "date_col": "Fecha",
        "desc_col": "Descripción",
        "cargo_col": "Cargo",
        "abono_col": "Abono",
        "date_fmt": "%d/%m/%Y",
        "banco": "Santander",
        "cuenta": "Cuenta Corriente",
        "moneda": "CLP",
    },
    "Santander Tarjeta Crédito": {
        "sep": ";",
        "date_col": "Fecha",
        "desc_col": "Descripción",
        "cargo_col": "Cargo",
        "abono_col": "Abono",
        "date_fmt": "%d/%m/%Y",
        "banco": "Santander",
        "cuenta": "Tarjeta Crédito",
        "moneda": "CLP",
    },
    "Genérico (configurar manualmente)": None,
}


def _try_parse_date(val, fmt: str):
    for f in [fmt, "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return pd.to_datetime(val, format=f)
        except Exception:
            pass
    try:
        return pd.to_datetime(val, dayfirst=True)
    except Exception:
        return pd.NaT


def _load_file(uploaded) -> pd.DataFrame | None:
    """Carga CSV o Excel y retorna un DataFrame crudo."""
    name = uploaded.name.lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            return pd.read_excel(uploaded, dtype=str)
        # CSV: intentar varios separadores
        content = uploaded.read()
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, encoding="utf-8-sig")
                if len(df.columns) > 1:
                    return df
            except Exception:
                pass
        return pd.read_csv(io.BytesIO(content), dtype=str, encoding="latin-1")
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None


def render():
    st.title("📂 Importar Cartola")
    st.caption("Sube un CSV o Excel descargado desde tu banco y lo importamos a Transacciones.")

    # ── Paso 1: subir archivo ─────────────────────────────────────────────────
    uploaded = st.file_uploader("Selecciona el archivo", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        st.info("Sube un archivo CSV o Excel de tu banco para comenzar.")
        return

    raw_df = _load_file(uploaded)
    if raw_df is None or raw_df.empty:
        return

    st.success(f"Archivo cargado: **{uploaded.name}** — {len(raw_df)} filas, {len(raw_df.columns)} columnas")

    with st.expander("Vista previa del archivo (primeras 5 filas)"):
        st.dataframe(raw_df.head(), use_container_width=True)

    # ── Paso 2: configurar mapeo de columnas ──────────────────────────────────
    st.subheader("Configurar columnas")
    preset_key = st.selectbox("Preset de banco", list(BANK_PRESETS.keys()))
    preset     = BANK_PRESETS[preset_key]

    cols = raw_df.columns.tolist()

    if preset:
        # Rellenar defaults del preset si la columna existe
        def _def(name):
            return cols.index(name) if name in cols else 0

        col1, col2 = st.columns(2)
        date_col = col1.selectbox("Columna Fecha", cols,
                                  index=_def(preset["date_col"]))
        desc_col = col2.selectbox("Columna Descripción", cols,
                                  index=_def(preset["desc_col"]))

        col3, col4 = st.columns(2)
        modo_monto = col3.radio("Tipo de montos",
                                ["Cargo y Abono (dos columnas)", "Monto único con signo"],
                                horizontal=True)
    else:
        col1, col2 = st.columns(2)
        date_col = col1.selectbox("Columna Fecha", cols)
        desc_col = col2.selectbox("Columna Descripción", cols)

        col3, col4 = st.columns(2)
        modo_monto = col3.radio("Tipo de montos",
                                ["Cargo y Abono (dos columnas)", "Monto único con signo"],
                                horizontal=True)

    if modo_monto == "Cargo y Abono (dos columnas)":
        cA, cB = st.columns(2)
        if preset:
            cargo_col = cA.selectbox("Col. Cargo (gasto)",  cols,
                                     index=cols.index(preset["cargo_col"]) if preset["cargo_col"] in cols else 0)
            abono_col = cB.selectbox("Col. Abono (ingreso)", cols,
                                     index=cols.index(preset["abono_col"]) if preset["abono_col"] in cols else 0)
        else:
            cargo_col = cA.selectbox("Col. Cargo (gasto)", cols)
            abono_col = cB.selectbox("Col. Abono (ingreso)", cols)
        monto_col   = None
        monto_signo = None
    else:
        cargo_col = None
        abono_col = None
        mA, mB = st.columns(2)
        monto_col   = mA.selectbox("Columna Monto", cols)
        monto_signo = mB.radio("Signo", ["Negativo = gasto", "Positivo = gasto"], horizontal=True)

    # Info del banco
    st.subheader("Metadatos")
    mA, mB, mC = st.columns(3)
    if preset:
        banco  = mA.text_input("Banco",   value=preset["banco"])
        cuenta = mB.text_input("Cuenta",  value=preset["cuenta"])
        moneda = mC.selectbox("Moneda", ["CLP", "USD"],
                              index=0 if preset["moneda"] == "CLP" else 1)
    else:
        banco  = mA.text_input("Banco",   value="Banco")
        cuenta = mB.text_input("Cuenta",  value="Cuenta")
        moneda = mC.selectbox("Moneda", ["CLP", "USD"])

    # ── Paso 3: procesar ──────────────────────────────────────────────────────
    if not st.button("🔄 Procesar y previsualizar", type="primary"):
        return

    # Parsear fechas y montos
    parsed_rows = []
    errors = 0
    for _, row in raw_df.iterrows():
        date_val = _try_parse_date(row.get(date_col, ""), "%d/%m/%Y")
        if pd.isna(date_val):
            errors += 1
            continue

        desc = str(row.get(desc_col, "")).strip()
        if not desc or desc.lower() in ("nan", ""):
            continue

        if cargo_col and abono_col:
            cargo = parse_clp_amount(row.get(cargo_col, ""))
            abono = parse_clp_amount(row.get(abono_col, ""))
            if cargo > 0:
                amount, tx_type = cargo, "Gasto"
            elif abono > 0:
                amount, tx_type = abono, "Ingreso"
            else:
                continue
        else:
            raw_amt = row.get(monto_col, "0")
            raw_str = str(raw_amt).strip().replace("$", "").replace(" ", "")
            is_neg  = raw_str.startswith("-")
            amount  = parse_clp_amount(raw_str.lstrip("-"))
            if monto_signo == "Negativo = gasto":
                tx_type = "Gasto" if is_neg else "Ingreso"
            else:
                tx_type = "Ingreso" if is_neg else "Gasto"

        parsed_rows.append({
            "fecha":      date_val.strftime("%Y-%m-%d"),
            "banco":      banco,
            "cuenta":     cuenta,
            "moneda":     moneda,
            "tipo":       tx_type,
            "descripcion": desc,
            "categoria":  "",   # se rellena después
            "monto":      amount,
        })

    if not parsed_rows:
        st.error("No se pudo parsear ninguna fila. Verifica el mapeo de columnas.")
        if errors:
            st.caption(f"{errors} filas con fecha inválida fueron omitidas.")
        return

    proc_df = pd.DataFrame(parsed_rows)

    # Aplicar categorización automática
    reglas_df = load_reglas_categorias()
    custom_rules = reglas_df.to_dict("records") if not reglas_df.empty else []
    proc_df["categoria"] = proc_df["descripcion"].apply(
        lambda d: categorize(d, custom_rules)
    )

    # ── Paso 4: deduplicación ─────────────────────────────────────────────────
    exist_df = load_transactions()
    n_dupes  = 0
    if not exist_df.empty:
        exist_keys = set(
            exist_df["fecha"].dt.strftime("%Y-%m-%d") + "|" +
            exist_df["descripcion"].astype(str) + "|" +
            exist_df["monto"].astype(str)
        )
        proc_df["_dup"] = proc_df.apply(
            lambda r: f"{r['fecha']}|{r['descripcion']}|{r['monto']}" in exist_keys, axis=1
        )
        n_dupes = proc_df["_dup"].sum()
    else:
        proc_df["_dup"] = False

    st.session_state["import_df"] = proc_df
    st.session_state["import_ready"] = True

    if errors:
        st.caption(f"⚠️ {errors} filas omitidas por fecha inválida.")
    if n_dupes:
        st.warning(f"⚠️ {n_dupes} transacciones ya existen en Sheets y están marcadas como duplicados.")

    st.success(f"✅ {len(proc_df)} transacciones procesadas — {n_dupes} posibles duplicados.")

    # ── Paso 5: previsualizar y corregir categorías ───────────────────────────
    st.subheader("Previsualizar y ajustar categorías")
    st.caption("Cambia las categorías si alguna fue mal asignada antes de importar.")

    edited_df = proc_df.copy()
    for i, row in proc_df.iterrows():
        bg = "#2d1a1a" if row["_dup"] else "transparent"
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([1.5, 3.5, 1.5, 2.5, 1])
            c1.markdown(
                f'<div style="background:{bg};padding:4px;border-radius:4px">{row["fecha"]}</div>',
                unsafe_allow_html=True
            )
            c2.markdown(
                f'<div style="background:{bg};padding:4px;border-radius:4px">{row["descripcion"][:55]}</div>',
                unsafe_allow_html=True
            )
            tipo_icon = "🟢" if row["tipo"] == "Ingreso" else "🔴"
            c3.markdown(f'{tipo_icon} ${row["monto"]:,.0f}')
            new_cat = c4.selectbox(
                "", CATEGORIES,
                index=CATEGORIES.index(row["categoria"]) if row["categoria"] in CATEGORIES else 0,
                key=f"imp_cat_{i}",
                label_visibility="collapsed"
            )
            edited_df.at[i, "categoria"] = new_cat
            if row["_dup"]:
                c5.caption("⚠️ dup")

    st.session_state["import_df_edited"] = edited_df

    # ── Paso 6: importar ──────────────────────────────────────────────────────
    st.markdown("---")
    only_new = st.checkbox("Importar solo filas nuevas (excluir duplicados)", value=True)
    c_imp, c_cancel = st.columns([2, 1])

    if c_imp.button("⬆️ Importar a Google Sheets", type="primary"):
        final_df = edited_df.copy()
        if only_new:
            final_df = final_df[~final_df["_dup"]]

        if final_df.empty:
            st.warning("No hay filas nuevas para importar.")
            return

        rows = [
            [row["fecha"], row["banco"], row["cuenta"], row["moneda"],
             row["tipo"], row["descripcion"], row["categoria"], row["monto"]]
            for _, row in final_df.iterrows()
        ]
        try:
            _append_rows("Transacciones", rows)
            st.cache_data.clear()
            st.success(f"🎉 {len(rows)} transacciones importadas exitosamente.")
            st.balloons()
        except Exception as e:
            st.error(f"Error al importar: {e}")
