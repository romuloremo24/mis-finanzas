"""Funciones de carga de datos con caché."""
import pandas as pd
import streamlit as st

from .config import SPREADSHEET_ID
from .sheets import get_sheets_service, _read_tab


@st.cache_data(ttl=300)
def load_transactions() -> pd.DataFrame:
    """Carga todas las transacciones desde la pestaña 'Transacciones' de Sheets."""
    try:
        svc = get_sheets_service()
        result = svc.values().get(
            spreadsheetId=SPREADSHEET_ID, range="'Transacciones'!A:H"
        ).execute()
        rows = result.get("values", [])
    except Exception as e:
        st.warning(f"No se pudo conectar a Google Sheets: {e}")
        return pd.DataFrame()

    if not rows or len(rows) < 2:
        return pd.DataFrame()

    cols = ["fecha", "banco", "cuenta", "moneda", "tipo", "descripcion", "categoria", "monto"]
    data = [r + [""] * (len(cols) - len(r)) for r in rows[1:]]
    df = pd.DataFrame(data, columns=cols)

    df["fecha"]    = pd.to_datetime(df["fecha"], errors="coerce")
    df["monto"]    = pd.to_numeric(
        df["monto"].astype(str).str.replace(",", "").str.replace("$", ""), errors="coerce"
    ).fillna(0).abs()
    df["moneda"]   = df["moneda"].replace("", "CLP").fillna("CLP")
    df["mes"]      = df["fecha"].dt.strftime("%Y-%m")
    df["es_gasto"] = df["tipo"] != "Ingreso"
    df = df.dropna(subset=["fecha"])
    return df


@st.cache_data(ttl=60)
def load_gastos_manuales() -> pd.DataFrame:
    df = _read_tab("Gastos_Manuales")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["mes"]   = df["fecha"].dt.strftime("%Y-%m")
        df = df.sort_values("fecha", ascending=False)
    return df


@st.cache_data(ttl=30)
def load_deudas() -> pd.DataFrame:
    df = _read_tab("Deudas")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.sort_values(["estado", "fecha_origen"], ascending=[True, False])
    return df


@st.cache_data(ttl=30)
def load_ingresos_esperados() -> pd.DataFrame:
    df = _read_tab("Ingresos_Esperados")
    if not df.empty:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
        df = df.sort_values("fecha_esperada")
    return df


@st.cache_data(ttl=120)
def load_reglas_categorias() -> pd.DataFrame:
    df = _read_tab("Reglas_Categorias")
    if not df.empty:
        df = df.sort_values("created_at", ascending=False)
    return df
