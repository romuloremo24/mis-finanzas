"""Lógica de categorización: reglas incorporadas + reglas personalizadas del usuario."""
from .config import CATEGORY_RULES


def categorize(description: str, custom_rules: list | None = None) -> str:
    """
    Categoriza una descripción de transacción.

    Orden de prioridad:
    1. Reglas personalizadas del usuario (Reglas_Categorias en Sheets)
    2. Reglas incorporadas (CATEGORY_RULES en config.py)
    3. "Otros" si no hay coincidencia
    """
    desc_lower = description.lower()

    if custom_rules:
        for rule in custom_rules:
            kw = str(rule.get("palabra_clave", "")).lower().strip()
            if kw and kw in desc_lower:
                return rule.get("categoria", "Otros")

    for category, keywords in CATEGORY_RULES.items():
        if any(kw in desc_lower for kw in keywords):
            return category

    return "Otros"


def apply_rules_to_df(df, desc_col: str = "descripcion", custom_rules: list | None = None):
    """
    Aplica categorización a un DataFrame y retorna la columna 'categoria'.
    Modifica el DataFrame in-place.
    """
    df["categoria"] = df[desc_col].astype(str).apply(
        lambda d: categorize(d, custom_rules)
    )
    return df


def parse_clp_amount(raw: str) -> float:
    """
    Parsea un monto en formato chileno a float.
    Maneja: "1.234.567", "1,234", "$15.000", "-15.000", vacío → 0.0
    """
    if not raw or str(raw).strip() in ("", "-", "nan"):
        return 0.0
    s = str(raw).strip().replace("$", "").replace(" ", "")
    # Si hay coma como decimal (ej: 15,50) y sólo una coma al final
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        # El punto es separador de miles
        s = s.replace(".", "").replace(",", "")
    try:
        return abs(float(s))
    except ValueError:
        return 0.0
