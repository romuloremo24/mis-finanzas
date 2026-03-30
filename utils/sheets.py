"""Capa de acceso a Google Sheets: cliente, CRUD y helpers."""
from datetime import datetime

import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import SERVICE_ACCOUNT_FILE, SPREADSHEET_ID, SCOPES, _LOCAL_TABS


@st.cache_resource
def get_sheets_service():
    """Soporta credenciales desde st.secrets (nube) o archivo local."""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds).spreadsheets()


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def init_sheets_tabs():
    """Crea las pestañas de datos manuales si no existen y escribe headers."""
    svc = get_sheets_service()
    meta = svc.get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    reqs = [
        {"addSheet": {"properties": {"title": name}}}
        for name in _LOCAL_TABS if name not in existing
    ]
    if reqs:
        svc.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": reqs}).execute()
    for tab, cols in _LOCAL_TABS.items():
        result = svc.values().get(
            spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1:A1"
        ).execute()
        if not result.get("values"):
            svc.values().update(
                spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1",
                valueInputOption="RAW", body={"values": [cols]}
            ).execute()


def _read_tab(tab: str) -> pd.DataFrame:
    svc = get_sheets_service()
    result = svc.values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:Z"
    ).execute()
    rows = result.get("values", [])
    cols = _LOCAL_TABS[tab]
    if len(rows) < 2:
        return pd.DataFrame(columns=cols)
    header = rows[0]
    data = [r + [""] * (len(header) - len(r)) for r in rows[1:]]
    return pd.DataFrame(data, columns=header)


def _write_tab(tab: str, df: pd.DataFrame):
    svc = get_sheets_service()
    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    svc.values().clear(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:Z").execute()
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1",
        valueInputOption="RAW", body={"values": values}
    ).execute()


def _append_row(tab: str, row: list):
    svc = get_sheets_service()
    svc.values().append(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:A",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [row]}
    ).execute()


def _append_rows(tab: str, rows: list):
    """Agrega múltiples filas en una sola llamada a la API."""
    if not rows:
        return
    svc = get_sheets_service()
    svc.values().append(
        spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A:A",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": rows}
    ).execute()


def _read_transacciones_raw() -> tuple[list, list]:
    """
    Retorna (header, rows_with_index) donde cada elemento de rows_with_index
    es (sheet_row_number, [valores...]).
    sheet_row_number es 1-indexed (fila 1 = header, fila 2 = primer dato).
    """
    svc = get_sheets_service()
    result = svc.values().get(
        spreadsheetId=SPREADSHEET_ID, range="'Transacciones'!A:H"
    ).execute()
    all_rows = result.get("values", [])
    if not all_rows:
        return [], []
    header = all_rows[0]
    indexed = [(i + 2, row) for i, row in enumerate(all_rows[1:])]
    return header, indexed


def _update_transaction_category(sheet_row: int, new_category: str):
    """Actualiza solo la celda Categoría (columna G) de una fila en Transacciones."""
    svc = get_sheets_service()
    svc.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'Transacciones'!G{sheet_row}",
        valueInputOption="RAW",
        body={"values": [[new_category]]}
    ).execute()
