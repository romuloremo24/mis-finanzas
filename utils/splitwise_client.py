"""Integracion con Splitwise API — gastos compartidos y desglose de transferencias."""
import os
from datetime import datetime, timedelta

import requests
import streamlit as st

API_BASE = "https://secure.splitwise.com/api/v3.0"


def _get_api_key() -> str | None:
    if "splitwise" in st.secrets:
        return st.secrets["splitwise"].get("api_key")
    return os.environ.get("SPLITWISE_API_KEY")


def _headers():
    key = _get_api_key()
    if not key:
        return None
    return {"Authorization": f"Bearer {key}"}


def is_configured() -> bool:
    return _get_api_key() is not None


@st.cache_data(ttl=300)
def get_current_user() -> dict | None:
    h = _headers()
    if not h:
        return None
    try:
        r = requests.get(f"{API_BASE}/get_current_user", headers=h, timeout=10)
        r.raise_for_status()
        return r.json().get("user", {})
    except Exception:
        return None


@st.cache_data(ttl=120)
def get_groups() -> list[dict]:
    h = _headers()
    if not h:
        return []
    try:
        r = requests.get(f"{API_BASE}/get_groups", headers=h, timeout=10)
        r.raise_for_status()
        return r.json().get("groups", [])
    except Exception:
        return []


@st.cache_data(ttl=120)
def get_expenses(dated_after: str = "", dated_before: str = "",
                 group_id: int = 0, limit: int = 200) -> list[dict]:
    """Obtiene gastos de Splitwise.

    Args:
        dated_after: YYYY-MM-DD
        dated_before: YYYY-MM-DD
        group_id: filtrar por grupo (0 = todos)
        limit: maximo de resultados
    """
    h = _headers()
    if not h:
        return []
    params = {"limit": limit}
    if dated_after:
        params["dated_after"] = f"{dated_after}T00:00:00Z"
    if dated_before:
        params["dated_before"] = f"{dated_before}T23:59:59Z"
    if group_id:
        params["group_id"] = group_id
    try:
        r = requests.get(f"{API_BASE}/get_expenses", headers=h, params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("expenses", [])
    except Exception:
        return []


def parse_expenses(raw_expenses: list[dict], user_id: int) -> list[dict]:
    """Convierte gastos de Splitwise a formato normalizado.

    Retorna lista de dicts con:
        date, description, total, currency, mi_parte, pagado_por_mi,
        category, group_name, splitwise_id
    """
    parsed = []
    for exp in raw_expenses:
        if exp.get("deleted_at"):
            continue
        if exp.get("payment"):
            continue

        total = float(exp.get("cost", 0))
        if total == 0:
            continue

        # Encontrar mi parte y si yo pague
        mi_parte = 0.0
        pagado_por_mi = 0.0
        for u in exp.get("users", []):
            if u.get("user_id") == user_id or u.get("user", {}).get("id") == user_id:
                mi_parte = float(u.get("owed_share", 0))
                pagado_por_mi = float(u.get("paid_share", 0))
                break

        # Categoria de Splitwise
        cat = exp.get("category", {})
        cat_name = cat.get("name", "General") if cat else "General"

        # Grupo
        group = exp.get("group_id")
        # No cachear group names aqui, se resuelve en la vista

        date_str = exp.get("date", "")[:10]  # YYYY-MM-DD

        parsed.append({
            "date": date_str,
            "description": exp.get("description", ""),
            "total": total,
            "currency": exp.get("currency_code", "CLP"),
            "mi_parte": mi_parte,
            "pagado_por_mi": pagado_por_mi,
            "category": cat_name,
            "group_id": group,
            "splitwise_id": exp.get("id"),
            "created_by": exp.get("created_by", {}).get("first_name", ""),
        })
    return parsed


def get_balances() -> list[dict]:
    """Obtiene balance con cada amigo (quien debe a quien)."""
    h = _headers()
    if not h:
        return []
    try:
        r = requests.get(f"{API_BASE}/get_friends", headers=h, timeout=10)
        r.raise_for_status()
        friends = r.json().get("friends", [])
        balances = []
        for f in friends:
            for b in f.get("balance", []):
                amount = float(b.get("amount", 0))
                if amount == 0:
                    continue
                balances.append({
                    "friend": f"{f.get('first_name', '')} {f.get('last_name', '')}".strip(),
                    "amount": amount,
                    "currency": b.get("currency_code", "CLP"),
                })
        return balances
    except Exception:
        return []


def match_transfers(splitwise_expenses: list[dict], bank_transactions: list) -> list[dict]:
    """Intenta vincular gastos de Splitwise con transferencias bancarias.

    Una transferencia bancaria puede cubrir multiples gastos de Splitwise
    si la suma de pagado_por_mi coincide con el monto de la transferencia
    dentro de un rango de +/- 3 dias y +/- 5% del monto.

    Retorna lista de matches: {transfer_idx, splitwise_ids, monto_transfer,
    monto_splitwise, desglose: [{desc, mi_parte, total}]}
    """
    if not splitwise_expenses or bank_transactions.empty:
        return []

    # Filtrar solo transferencias bancarias
    transfers = bank_transactions[
        (bank_transactions["tipo"] == "Gasto") &
        (bank_transactions["categoria"].isin(["Transferencias"]))
    ].copy()

    if transfers.empty:
        return []

    matches = []
    used_sw = set()

    for idx, tx in transfers.iterrows():
        tx_date = tx["fecha"]
        tx_amount = tx["monto"]

        # Buscar gastos de Splitwise donde yo pague, en ventana de 3 dias
        candidates = []
        for sw in splitwise_expenses:
            if sw["splitwise_id"] in used_sw:
                continue
            if sw["pagado_por_mi"] <= 0:
                continue
            try:
                sw_date = datetime.strptime(sw["date"], "%Y-%m-%d")
                diff = abs((tx_date - sw_date).days)
                if diff <= 3:
                    candidates.append(sw)
            except Exception:
                continue

        if not candidates:
            continue

        # Intentar match exacto primero (un gasto = una transferencia)
        for sw in candidates:
            ratio = sw["pagado_por_mi"] / tx_amount if tx_amount > 0 else 0
            if 0.95 <= ratio <= 1.05:
                matches.append({
                    "transfer_fecha": tx_date.strftime("%Y-%m-%d"),
                    "transfer_desc": tx["descripcion"],
                    "transfer_monto": tx_amount,
                    "splitwise_total": sw["pagado_por_mi"],
                    "desglose": [{
                        "desc": sw["description"],
                        "mi_parte": sw["mi_parte"],
                        "total": sw["total"],
                        "category": sw["category"],
                    }],
                })
                used_sw.add(sw["splitwise_id"])
                break

        # Si no hay match exacto, intentar combinar multiples gastos
        if not any(m["transfer_desc"] == tx["descripcion"] for m in matches):
            sorted_cands = sorted(candidates, key=lambda x: x["pagado_por_mi"], reverse=True)
            combo = []
            combo_total = 0.0
            for sw in sorted_cands:
                if combo_total + sw["pagado_por_mi"] <= tx_amount * 1.05:
                    combo.append(sw)
                    combo_total += sw["pagado_por_mi"]
                    if combo_total >= tx_amount * 0.95:
                        break

            if combo and 0.90 <= combo_total / tx_amount <= 1.10:
                matches.append({
                    "transfer_fecha": tx_date.strftime("%Y-%m-%d"),
                    "transfer_desc": tx["descripcion"],
                    "transfer_monto": tx_amount,
                    "splitwise_total": combo_total,
                    "desglose": [{
                        "desc": sw["description"],
                        "mi_parte": sw["mi_parte"],
                        "total": sw["total"],
                        "category": sw["category"],
                    } for sw in combo],
                })
                for sw in combo:
                    used_sw.add(sw["splitwise_id"])

    return matches
