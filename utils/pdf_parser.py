"""Extraccion de transacciones desde PDFs bancarios (Lider BCI, Santander)."""
import os
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from .categorias import categorize
from .config import BASE_DIR

INPUT_DIR = BASE_DIR / "estados_de_cuenta"

BANK_FOLDERS = {
    "Lider_BCI": {"name": "Lider BCI", "password": os.environ.get("BCI_PDF_PASSWORD", ""), "account_type": "Tarjeta Crédito"},
    "Santander":  {"name": "Santander", "password": os.environ.get("SANTANDER_PDF_PASSWORD", ""), "account_type": None},
}

SANTANDER_ACCOUNT_SUFFIXES = {
    "_CC": "Cuenta Corriente",
    "_CM": "Cuenta Vista",
    "_CV": "Cuenta Vista",
    "_TC": "Tarjeta Crédito",
    "_MC": "Tarjeta Crédito",
}


def _detect_account_type(filename: str) -> str:
    stem = Path(filename).stem.upper()
    if stem.startswith("80_"):
        return "Tarjeta Crédito"
    for suffix, label in SANTANDER_ACCOUNT_SUFFIXES.items():
        if stem.endswith(suffix):
            return label
    return "Cuenta"


def parse_pdf_file(path: str | Path, banco: str = "", password: str = "") -> list[dict]:
    """Parsea un PDF bancario y retorna lista de transacciones.

    Cada transaccion es un dict con: date, description, amount, bank,
    account_type, tx_type, category, currency.
    """
    path = Path(path)
    if not banco:
        banco = _detect_bank(path)
    account_type = _detect_account_type(path.name)

    # Detectar banco de la carpeta padre si no se especifico
    for folder_name, config in BANK_FOLDERS.items():
        if folder_name.lower() in str(path.parent).lower():
            banco = banco or config["name"]
            password = password or config.get("password", "")
            if config["account_type"]:
                account_type = config["account_type"]
            break

    transactions = []
    try:
        with pdfplumber.open(str(path), password=password or None) as pdf:
            if "lider" in banco.lower() or "bci" in banco.lower():
                transactions = _parse_lider_bci(pdf, banco, account_type)
            elif "santander" in banco.lower():
                fname = path.name.upper()
                if fname.startswith("80_15358"):
                    transactions = _parse_santander_tc_cl(pdf, banco, account_type)
                elif fname.startswith("80_15356"):
                    transactions = _parse_santander_tc_usd(pdf, banco, account_type)
                else:
                    transactions = _parse_santander(pdf, banco, account_type)
            else:
                # Intentar detectar por contenido
                transactions = _parse_generic(pdf, banco, account_type)
    except Exception:
        pass

    return transactions


def _detect_bank(path: Path) -> str:
    name = path.name.lower()
    parent = path.parent.name.lower()
    if "lider" in parent or "bci" in parent or "lider" in name:
        return "Lider BCI"
    if "santander" in parent or "santander" in name:
        return "Santander"
    return "Banco"


def _parse_lider_bci(pdf, bank, account_type):
    transactions = []
    for page in pdf.pages:
        for table in page.extract_tables():
            if not table:
                continue
            header = [str(c or "").lower() for c in table[0]]
            if not any("fecha" in h for h in header):
                continue
            fecha_col = next((i for i, h in enumerate(header) if "fecha" in h), None)
            desc_col = next((i for i, h in enumerate(header) if "descripci" in h), None)
            amount_col = len(table[0]) - 1
            if fecha_col is None:
                continue
            all_dates, all_descs, all_amounts = [], [], []
            for row in table[2:]:
                if not row:
                    continue
                if row[fecha_col]:
                    for d in str(row[fecha_col]).split("\n"):
                        d = d.strip()
                        if re.match(r"\d{2}/\d{2}/\d{4}", d):
                            all_dates.append(d)
                if desc_col is not None and row[desc_col]:
                    for d in str(row[desc_col]).split("\n"):
                        d = d.strip()
                        if d and not _is_section_header(d):
                            all_descs.append(d)
                if row[amount_col]:
                    for a in str(row[amount_col]).split("\n"):
                        a = a.strip()
                        if re.search(r"\d", a):
                            all_amounts.append(a)
            for date_s, desc_s, amt_s in zip(all_dates, all_descs, all_amounts):
                date = _parse_date(date_s)
                amount = _parse_amount_cl(amt_s)
                if date and amount:
                    transactions.append({
                        "date": date, "description": desc_s,
                        "amount": amount, "bank": bank,
                        "account_type": account_type,
                        "tx_type": "Gasto", "category": categorize(desc_s, []),
                        "currency": "CLP",
                    })
    return transactions


def _is_section_header(text):
    t = text.strip()
    return (t.isupper() and len(t) < 30 and not any(c.isdigit() for c in t)) or \
           bool(re.match(r"^\d+\.\s+Total", t, re.IGNORECASE))


def _parse_santander(pdf, bank, account_type):
    transactions = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        year = _extract_year(text)
        for table in page.extract_tables():
            if not table or len(table) < 2:
                continue
            header = [str(c or "").upper() for c in table[0]]
            if "FECHA" not in header:
                continue
            fecha_col = header.index("FECHA")
            desc_col = next((i for i, h in enumerate(header) if "DESCRIPCION" in h or "DESCRIPCIÓN" in h), None)
            cargo_col = next((i for i, h in enumerate(header) if "CARGOS" in h or ("CHEQUES" in h and "OTROS" in h)), None)
            abono_col = next((i for i, h in enumerate(header) if "ABONOS" in h or ("DEPOSITOS" in h and "OTROS" in h)), None)
            if desc_col is None:
                continue
            data_row = table[1]
            if not data_row:
                continue
            fechas = _split_cell(data_row[fecha_col])
            descs = _split_cell(data_row[desc_col])
            cargos = _split_amounts(data_row[cargo_col] if cargo_col is not None else "")
            abonos = _split_amounts(data_row[abono_col] if abono_col is not None else "")
            cargo_idx, abono_idx = 0, 0
            for i, desc in enumerate(descs):
                if not desc or "Saldo Dia" in desc or "***" in desc or "Resumen" in desc:
                    continue
                fecha_s = fechas[i] if i < len(fechas) else ""
                date = _parse_date_santander(fecha_s, year)
                if not date:
                    continue
                is_abono = any(kw in desc for kw in [
                    "Rescate Fondos", "Traspaso Internet desde", "REMUNERACION",
                    "Transf.", "Transf de", "PAGO PROVEEDOR",
                ])
                if is_abono and abono_idx < len(abonos):
                    amount = abonos[abono_idx]
                    abono_idx += 1
                elif cargo_idx < len(cargos):
                    amount = cargos[cargo_idx]
                    cargo_idx += 1
                else:
                    continue
                if amount:
                    transactions.append({
                        "date": date, "description": desc,
                        "amount": amount, "bank": bank,
                        "account_type": account_type,
                        "tx_type": "Ingreso" if is_abono else "Gasto",
                        "category": categorize(desc, []),
                        "currency": "CLP",
                    })
    return transactions


def _parse_santander_tc_cl(pdf, bank, account_type):
    transactions = []
    SKIP_DESC = {"PRODUCTOS", "CARGOS, COMISIONES", "INFORMACION COMPRAS"}
    for page in pdf.pages:
        for table in page.extract_tables():
            if not table or len(table) < 4:
                continue
            header_text = " ".join(str(c or "") for c in table[0]).upper()
            if "PERIODO ACTUAL" not in header_text:
                continue
            row1 = [str(c or "").upper() for c in table[1]]
            fecha_col = next((i for i, h in enumerate(row1) if "FECHA" in h), 1)
            desc_col = next((i for i, h in enumerate(row1) if "DESCRIPCI" in h), 2)
            for data_row in table[3:]:
                if not data_row:
                    continue
                first = str(data_row[0] or "").upper()
                if any(s in first for s in SKIP_DESC):
                    continue
                fechas = _split_cell(data_row[fecha_col] if fecha_col < len(data_row) else "")
                descs = _split_cell(data_row[desc_col] if desc_col < len(data_row) else "")
                cancelados = _split_amounts(data_row[3] if len(data_row) > 3 else "")
                cuotas = _split_amounts(data_row[-1] if data_row else "")
                cancelado_idx = cuota_idx = 0
                for i, desc in enumerate(descs):
                    desc = desc.strip()
                    if not desc or any(s in desc.upper() for s in SKIP_DESC):
                        continue
                    fecha_s = fechas[i] if i < len(fechas) else ""
                    date = _parse_date(fecha_s)
                    if not date:
                        continue
                    if "MONTO CANCELADO" in desc.upper():
                        if cancelado_idx >= len(cancelados):
                            continue
                        amount = abs(cancelados[cancelado_idx])
                        cancelado_idx += 1
                        tx_type, category = "Ingreso", "Transferencias"
                    else:
                        if cuota_idx >= len(cuotas):
                            continue
                        amount = cuotas[cuota_idx]
                        cuota_idx += 1
                        tx_type = "Gasto"
                        category = categorize(desc, [])
                    if amount:
                        transactions.append({
                            "date": date, "description": desc,
                            "amount": amount, "bank": bank,
                            "account_type": account_type,
                            "tx_type": tx_type, "category": category,
                            "currency": "CLP",
                        })
    return transactions


def _parse_santander_tc_usd(pdf, bank, account_type):
    transactions = []
    SKIP_FIRST = {"1. TOTAL OPERACIONES", "MOVIMIENTOS TARJETA", "3. CARGOS"}
    for page in pdf.pages:
        for table in page.extract_tables():
            if not table or len(table) < 2:
                continue
            header_text = " ".join(str(c or "") for c in table[0]).upper()
            if "INFORMACION DE TRANSACCIONES" not in header_text:
                continue
            row1 = [str(c or "").upper() for c in table[1]]
            fecha_col = next((i for i, h in enumerate(row1) if "FECHA" in h), 0)
            desc_col = next((i for i, h in enumerate(row1) if "DESCRIPCI" in h), 1)
            amount_col = next((i for i, h in enumerate(row1) if "US$" in h or "MONTO US" in h), len(row1) - 1)
            for data_row in table[2:]:
                if not data_row:
                    continue
                first = str(data_row[0] or "").upper()
                if any(s in first for s in SKIP_FIRST):
                    continue
                fechas = _split_cell(data_row[fecha_col] if fecha_col < len(data_row) else "")
                descs = _split_cell(data_row[desc_col] if desc_col < len(data_row) else "")
                amts_raw = _split_cell(data_row[amount_col] if amount_col < len(data_row) else "")
                for i, desc in enumerate(descs):
                    desc = desc.strip()
                    if not desc:
                        continue
                    fecha_s = fechas[i] if i < len(fechas) else ""
                    date = _parse_date(fecha_s)
                    if not date:
                        continue
                    if i >= len(amts_raw):
                        continue
                    amount = _parse_amount_usd(amts_raw[i])
                    if amount is None:
                        continue
                    if amount < 0:
                        tx_type, category = "Ingreso", "Transferencias"
                        amount = abs(amount)
                    else:
                        tx_type = "Gasto"
                        category = categorize(desc, [])
                    if amount:
                        transactions.append({
                            "date": date, "description": desc,
                            "amount": amount, "bank": bank,
                            "account_type": account_type + " (USD)",
                            "tx_type": tx_type, "category": category,
                            "currency": "USD",
                        })
    return transactions


def _parse_generic(pdf, bank, account_type):
    """Intenta extraer transacciones de un PDF generico buscando patrones de fecha+monto."""
    transactions = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            m = re.match(r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d.,]+)\s*$", line.strip())
            if m:
                date = _parse_date(m.group(1))
                desc = m.group(2).strip()
                amount = _parse_amount_cl(m.group(3))
                if date and amount:
                    transactions.append({
                        "date": date, "description": desc,
                        "amount": amount, "bank": bank,
                        "account_type": account_type,
                        "tx_type": "Gasto", "category": categorize(desc, []),
                        "currency": "CLP",
                    })
    return transactions


# ── Utilidades ────────────────────────────────────────────────────────────────
def _split_cell(cell):
    if not cell:
        return []
    return [v.strip() for v in str(cell).split("\n") if v.strip()]


def _split_amounts(cell):
    amounts = []
    for raw in _split_cell(cell):
        v = _parse_amount_cl(raw)
        if v is not None:
            amounts.append(v)
    return amounts


def _extract_year(text):
    m = re.search(r"\d{2}/\d{2}/(\d{4})", text)
    return m.group(1) if m else str(datetime.now().year)


def _parse_date_santander(raw, year):
    raw = raw.strip()
    if re.match(r"^\d{2}/\d{2}$", raw):
        return _parse_date(f"{raw}/{year}")
    return _parse_date(raw)


def _parse_date(raw):
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_amount_cl(raw):
    try:
        cleaned = re.sub(r"\s+", "", str(raw))
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        cleaned = cleaned.replace(".", "")
        if not cleaned or cleaned == "-":
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _parse_amount_usd(raw):
    try:
        cleaned = re.sub(r"\s+", "", str(raw))
        cleaned = re.sub(r"[^0-9,.\-]", "", cleaned)
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(".", "")
        if not cleaned or cleaned == "-":
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None
