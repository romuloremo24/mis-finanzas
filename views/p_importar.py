"""Pagina: Importacion de cartolas bancarias desde CSV, Excel o PDF."""
from datetime import datetime
from pathlib import Path
import io
import os

import pandas as pd
import streamlit as st

from utils.categorias import categorize, parse_clp_amount
from utils.config import CATEGORIES, ACCOUNT_TYPES, C_CARD, C_BORDER, BASE_DIR
from utils.loaders import load_transactions, load_reglas_categorias, load_documentos
from utils.sheets import _append_rows, _append_row, _new_id

ESTADOS_DIR = BASE_DIR / "estados_de_cuenta"

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
    "Santander Tarjeta Crédito USD": {
        "sep": ";",
        "date_col": "Fecha",
        "desc_col": "Descripción",
        "cargo_col": "Cargo",
        "abono_col": "Abono",
        "date_fmt": "%d/%m/%Y",
        "banco": "Santander",
        "cuenta": "Tarjeta Crédito",
        "moneda": "USD",
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
    name = uploaded.name.lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            return pd.read_excel(uploaded, dtype=str)
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


def _detect_existing_docs(banco: str, cuenta: str, periodo: str) -> pd.DataFrame:
    docs = load_documentos()
    if docs.empty:
        return pd.DataFrame()
    match = docs[
        (docs["banco"] == banco) &
        (docs["cuenta"] == cuenta) &
        (docs["periodo"] == periodo)
    ]
    return match


def _determine_doc_status(fecha_desde: str, existing_docs: pd.DataFrame) -> str:
    if not existing_docs.empty:
        return "reimportado"
    try:
        from_date = pd.Timestamp(fecha_desde)
        now = pd.Timestamp.now()
        diff_days = (now - from_date).days
        if diff_days > 60:
            return "antiguo"
    except Exception:
        pass
    return "nuevo"


def _save_pdf_locally(uploaded, banco: str) -> str | None:
    """Guarda el PDF subido en estados_de_cuenta/{banco}/ y retorna la ruta."""
    folder_map = {
        "BCI": "Lider_BCI",
        "Lider BCI": "Lider_BCI",
        "Santander": "Santander",
    }
    folder_name = folder_map.get(banco, banco.replace(" ", "_"))
    dest_dir = ESTADOS_DIR / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / uploaded.name
    dest_path.write_bytes(uploaded.getvalue())
    return str(dest_path)


def _parse_pdf(uploaded, banco: str, password: str = "") -> list[dict]:
    """Parsea un PDF bancario usando el modulo pdf_parser."""
    try:
        from utils.pdf_parser import parse_pdf_file
    except ImportError:
        st.error("pdfplumber no esta instalado. Ejecuta: pip install pdfplumber")
        return []

    # Guardar temporalmente para parsear
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    try:
        return parse_pdf_file(tmp_path, banco=banco, password=password)
    finally:
        os.unlink(tmp_path)


def render():
    st.title("📂 Importar Cartola")
    st.caption("Sube un CSV, Excel o **PDF** de tu banco y lo importamos a Transacciones.")

    # ── Paso 1: subir archivo ─────────────────────────────────────────────────
    uploaded = st.file_uploader("Selecciona el archivo", type=["csv", "xlsx", "xls", "pdf"])
    if uploaded is None:
        st.info("Sube un archivo CSV, Excel o PDF de tu banco para comenzar.")
        _show_recent_imports()
        return

    is_pdf = uploaded.name.lower().endswith(".pdf")

    # ── Flujo PDF ─────────────────────────────────────────────────────────────
    if is_pdf:
        _render_pdf_flow(uploaded)
        return

    # ── Flujo CSV/Excel ───────────────────────────────────────────────────────
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
            "categoria":  "",
            "monto":      amount,
        })

    if not parsed_rows:
        st.error("No se pudo parsear ninguna fila. Verifica el mapeo de columnas.")
        if errors:
            st.caption(f"{errors} filas con fecha inválida fueron omitidas.")
        return

    proc_df = pd.DataFrame(parsed_rows)

    # Calcular periodo y rango
    proc_df["_fecha_dt"] = pd.to_datetime(proc_df["fecha"])
    fecha_desde = proc_df["_fecha_dt"].min()
    fecha_hasta = proc_df["_fecha_dt"].max()
    periodo = fecha_desde.strftime("%Y-%m")
    if fecha_desde.month != fecha_hasta.month or fecha_desde.year != fecha_hasta.year:
        periodo = f"{fecha_desde.strftime('%Y-%m')} a {fecha_hasta.strftime('%Y-%m')}"

    # Detectar si ya existe este documento
    existing_docs = _detect_existing_docs(banco, cuenta, periodo)
    doc_status = _determine_doc_status(proc_df["fecha"].min(), existing_docs)
    tipo_cuenta = ACCOUNT_TYPES.get(cuenta, cuenta)

    # ── Alerta de documento existente / antiguo ───────────────────────────────
    if doc_status == "reimportado":
        prev = existing_docs.iloc[0]
        st.warning(
            f"⚠️ **Documento ya importado** — Ya existe una cartola de **{banco} {cuenta}** "
            f"para el periodo **{periodo}** (importada el {prev['fecha_importacion']}).\n\n"
            f"Si continuas, se marcara como **reimportado**. Revisa los duplicados abajo."
        )
    elif doc_status == "antiguo":
        st.info(
            f"📋 **Cartola antigua detectada** — Este documento es de **{periodo}** "
            f"(hace mas de 60 dias). Se marcara como **antiguo** en el registro."
        )
    else:
        st.success(f"🆕 **Documento nuevo** — Periodo: **{periodo}** | {banco} {cuenta} ({tipo_cuenta})")

    # Resumen del documento
    st.markdown(f"""
    <div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:10px;padding:16px;margin:8px 0">
        <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div><span style="color:#888;font-size:11px">ARCHIVO</span><br>
                 <b style="color:#fff">{uploaded.name}</b></div>
            <div><span style="color:#888;font-size:11px">BANCO</span><br>
                 <b style="color:#fff">{banco}</b></div>
            <div><span style="color:#888;font-size:11px">CUENTA</span><br>
                 <b style="color:#fff">{cuenta}</b></div>
            <div><span style="color:#888;font-size:11px">TIPO</span><br>
                 <b style="color:#fff">{tipo_cuenta}</b></div>
            <div><span style="color:#888;font-size:11px">PERIODO</span><br>
                 <b style="color:#fff">{periodo}</b></div>
            <div><span style="color:#888;font-size:11px">RANGO</span><br>
                 <b style="color:#fff">{fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}</b></div>
            <div><span style="color:#888;font-size:11px">TRANSACCIONES</span><br>
                 <b style="color:#fff">{len(proc_df)}</b></div>
            <div><span style="color:#888;font-size:11px">ESTADO</span><br>
                 <b style="color:{'#2ecc71' if doc_status == 'nuevo' else '#f39c12' if doc_status == 'antiguo' else '#3498db'}">{doc_status.upper()}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Aplicar categorizacion automatica
    reglas_df = load_reglas_categorias()
    custom_rules = reglas_df.to_dict("records") if not reglas_df.empty else []
    proc_df["categoria"] = proc_df["descripcion"].apply(
        lambda d: categorize(d, custom_rules)
    )

    # ── Paso 4: deduplicacion ─────────────────────────────────────────────────
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
    st.session_state["import_meta"] = {
        "nombre_archivo": uploaded.name,
        "banco": banco,
        "cuenta": cuenta,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
        "periodo": periodo,
        "fecha_desde": fecha_desde.strftime("%Y-%m-%d"),
        "fecha_hasta": fecha_hasta.strftime("%Y-%m-%d"),
        "doc_status": doc_status,
    }

    if errors:
        st.caption(f"⚠️ {errors} filas omitidas por fecha invalida.")
    if n_dupes:
        st.warning(f"⚠️ {n_dupes} transacciones ya existen en Sheets y estan marcadas como duplicados.")

    st.success(f"✅ {len(proc_df)} transacciones procesadas — {n_dupes} posibles duplicados.")

    # ── Paso 5: previsualizar y corregir categorias ───────────────────────────
    st.subheader("Previsualizar y ajustar categorias")
    st.caption("Cambia las categorias si alguna fue mal asignada antes de importar.")

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

            # Registrar documento en Documentos_Cargados
            meta = st.session_state.get("import_meta", {})
            total_gastos = final_df[final_df["tipo"] == "Gasto"]["monto"].sum()
            total_ingresos = final_df[final_df["tipo"] == "Ingreso"]["monto"].sum()

            doc_row = [
                _new_id(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                meta.get("nombre_archivo", uploaded.name),
                meta.get("banco", banco),
                meta.get("cuenta", cuenta),
                meta.get("tipo_cuenta", ACCOUNT_TYPES.get(cuenta, cuenta)),
                meta.get("moneda", moneda),
                meta.get("periodo", periodo),
                meta.get("fecha_desde", ""),
                meta.get("fecha_hasta", ""),
                len(final_df),
                round(total_gastos),
                round(total_ingresos),
                meta.get("doc_status", "nuevo"),
                "",
            ]
            _append_row("Documentos_Cargados", doc_row)

            st.cache_data.clear()
            st.success(f"🎉 {len(rows)} transacciones importadas y documento registrado exitosamente.")
            st.balloons()
        except Exception as e:
            st.error(f"Error al importar: {e}")


def _render_pdf_flow(uploaded):
    """Flujo de importacion para archivos PDF bancarios."""
    st.success(f"PDF cargado: **{uploaded.name}**")

    st.subheader("Configurar banco")
    col_b, col_p = st.columns(2)
    banco = col_b.selectbox("Banco", ["Lider BCI", "Santander", "Otro"], key="pdf_banco")
    password = col_p.text_input("Contraseña del PDF (si tiene)", type="password", key="pdf_pass")

    # Opcion para guardar localmente
    save_local = st.checkbox(
        "Guardar PDF en carpeta local (estados_de_cuenta/)",
        value=True,
        help="Guarda una copia en tu PC para tener respaldo organizado por banco"
    )

    if not st.button("🔄 Extraer transacciones del PDF", type="primary"):
        return

    with st.spinner("Extrayendo transacciones del PDF..."):
        transactions = _parse_pdf(uploaded, banco, password)

    if not transactions:
        st.error(
            "No se pudieron extraer transacciones del PDF. "
            "Verifica que el banco es correcto y la contraseña (si aplica)."
        )
        st.caption("Bancos soportados: Lider BCI, Santander (CC, TC CLP, TC USD)")
        return

    # Guardar PDF localmente si se pidio
    saved_path = None
    if save_local:
        saved_path = _save_pdf_locally(uploaded, banco)
        if saved_path:
            st.caption(f"PDF guardado en: `{saved_path}`")

    # Convertir a DataFrame
    proc_df = pd.DataFrame([{
        "fecha": t["date"],
        "banco": t["bank"],
        "cuenta": t["account_type"],
        "moneda": t.get("currency", "CLP"),
        "tipo": t["tx_type"],
        "descripcion": t["description"],
        "categoria": t["category"],
        "monto": t["amount"],
    } for t in transactions])

    # Calcular metadata
    proc_df["_fecha_dt"] = pd.to_datetime(proc_df["fecha"])
    fecha_desde = proc_df["_fecha_dt"].min()
    fecha_hasta = proc_df["_fecha_dt"].max()
    periodo = fecha_desde.strftime("%Y-%m")
    cuenta = proc_df["cuenta"].iloc[0] if not proc_df.empty else ""
    moneda = proc_df["moneda"].iloc[0] if not proc_df.empty else "CLP"
    tipo_cuenta = ACCOUNT_TYPES.get(cuenta, cuenta)

    if fecha_desde.month != fecha_hasta.month or fecha_desde.year != fecha_hasta.year:
        periodo = f"{fecha_desde.strftime('%Y-%m')} a {fecha_hasta.strftime('%Y-%m')}"

    # Detectar documento existente
    existing_docs = _detect_existing_docs(banco, cuenta, periodo)
    doc_status = _determine_doc_status(proc_df["fecha"].min(), existing_docs)

    if doc_status == "reimportado":
        st.warning(f"⚠️ Ya existe una cartola de **{banco} {cuenta}** para **{periodo}**. Se marcara como reimportado.")
    elif doc_status == "antiguo":
        st.info(f"📋 Cartola antigua detectada — periodo **{periodo}**.")

    st.success(f"✅ {len(proc_df)} transacciones extraidas del PDF")

    # Resumen
    st.markdown(f"""
    <div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:10px;padding:16px;margin:8px 0">
        <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div><span style="color:#888;font-size:11px">BANCO</span><br><b style="color:#fff">{banco}</b></div>
            <div><span style="color:#888;font-size:11px">CUENTA</span><br><b style="color:#fff">{cuenta}</b></div>
            <div><span style="color:#888;font-size:11px">TIPO</span><br><b style="color:#fff">{tipo_cuenta}</b></div>
            <div><span style="color:#888;font-size:11px">PERIODO</span><br><b style="color:#fff">{periodo}</b></div>
            <div><span style="color:#888;font-size:11px">RANGO</span><br><b style="color:#fff">{fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}</b></div>
            <div><span style="color:#888;font-size:11px">TRANSACCIONES</span><br><b style="color:#fff">{len(proc_df)}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Deduplicacion
    exist_df = load_transactions()
    n_dupes = 0
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

    if n_dupes:
        st.warning(f"⚠️ {n_dupes} duplicados detectados.")

    # Preview
    st.subheader("Vista previa")
    disp = proc_df.copy()
    disp["tipo_icon"] = disp["tipo"].apply(lambda t: "🟢" if t == "Ingreso" else "🔴")
    disp["monto_fmt"] = disp["monto"].apply(lambda v: f"${v:,.0f}")
    st.dataframe(
        disp[["fecha", "descripcion", "categoria", "tipo_icon", "monto_fmt", "_dup"]].rename(columns={
            "fecha": "Fecha", "descripcion": "Descripcion", "categoria": "Categoria",
            "tipo_icon": "Tipo", "monto_fmt": "Monto", "_dup": "Duplicado"
        }),
        hide_index=True, use_container_width=True, height=350,
    )

    # Importar
    st.markdown("---")
    only_new = st.checkbox("Importar solo filas nuevas (excluir duplicados)", value=True, key="pdf_only_new")

    if st.button("⬆️ Importar a Google Sheets", type="primary", key="pdf_import"):
        final_df = proc_df[~proc_df["_dup"]] if only_new else proc_df.copy()
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

            total_gastos = final_df[final_df["tipo"] == "Gasto"]["monto"].sum()
            total_ingresos = final_df[final_df["tipo"] == "Ingreso"]["monto"].sum()
            doc_row = [
                _new_id(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                uploaded.name,
                banco,
                cuenta,
                tipo_cuenta,
                moneda,
                periodo,
                fecha_desde.strftime("%Y-%m-%d"),
                fecha_hasta.strftime("%Y-%m-%d"),
                len(final_df),
                round(total_gastos),
                round(total_ingresos),
                doc_status,
                f"PDF {'guardado' if saved_path else 'no guardado'} localmente",
            ]
            _append_row("Documentos_Cargados", doc_row)

            st.cache_data.clear()
            st.success(f"🎉 {len(rows)} transacciones importadas desde PDF.")
            st.balloons()
        except Exception as e:
            st.error(f"Error al importar: {e}")


def _show_recent_imports():
    docs = load_documentos()
    if docs.empty:
        return
    st.markdown("---")
    st.subheader("📋 Ultimas importaciones")
    recent = docs.head(5).copy()
    recent["fecha_importacion"] = recent["fecha_importacion"].dt.strftime("%d/%m/%Y %H:%M")
    status_map = {"nuevo": "🟢", "antiguo": "🟠", "reimportado": "🔵"}
    recent["estado"] = recent["estado"].map(status_map).fillna("") + " " + recent["estado"]
    st.dataframe(
        recent[["periodo", "banco", "cuenta", "tipo_cuenta", "num_transacciones", "estado", "fecha_importacion"]].rename(
            columns={
                "periodo": "Periodo", "banco": "Banco", "cuenta": "Cuenta",
                "tipo_cuenta": "Tipo", "num_transacciones": "# Tx",
                "estado": "Estado", "fecha_importacion": "Importado",
            }
        ),
        hide_index=True, use_container_width=True,
    )
