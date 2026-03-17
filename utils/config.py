"""Constantes y configuración global de la plataforma."""
from pathlib import Path

BASE_DIR             = Path(__file__).parent.parent
SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"
SPREADSHEET_ID       = "1sGlIewugpDLfvoXopec4UQxhFgCMbf1rQ9wgdDYxpCk"
SCOPES               = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Pestañas de datos manuales (se crean automáticamente) ─────────────────────
_LOCAL_TABS = {
    "Gastos_Manuales":    ["id","fecha","descripcion","monto","moneda","categoria","metodo_pago","notas"],
    "Deudas":             ["id","tipo","nombre","descripcion","monto","moneda","fecha_origen","fecha_vencimiento","estado","notas"],
    "Ingresos_Esperados": ["id","nombre","descripcion","monto","moneda","fecha_esperada","recurrente","estado","notas"],
    "Reglas_Categorias":  ["id","palabra_clave","categoria","created_at"],
}

# ── Opciones de formularios ────────────────────────────────────────────────────
CATEGORIES = [
    "Supermercado", "Restaurante", "Combustible", "Transporte",
    "Farmacia", "Salud", "Deporte", "Entretención", "Ropa/Calzado",
    "Educación", "Servicios", "Hogar", "Mascotas",
    "Inversiones/Ahorro", "Viajes/Turismo", "Transferencias",
    "Banco/Comisiones", "Seguros", "Donaciones", "Retail",
    "Sueldo/Salario", "Rendiciones/Reembolsos", "Otros",
]

PAYMENT_METHODS = ["Efectivo", "Débito", "Crédito", "Transferencia", "Otro"]

# ── Reglas de categorización incorporadas ─────────────────────────────────────
CATEGORY_RULES = {
    "Rendiciones/Reembolsos": ["rendicion", "reembolso viatico", "reembolso viático"],
    "Inversiones/Ahorro":     ["fintual", "fondo mutuo", "rescate fondos", "deposito ahorro", "cuenta ahorro"],
    "Viajes/Turismo":         ["viajes falabella", "despegar", "airbnb", "booking.com", "latam", "sky airline",
                               "aeropuerto", "hotel", "hostal", "agencia viaje"],
    "Supermercado":           ["lider", "jumbo", "unimarc", "santa isabel", "tottus", "acuenta"],
    "Restaurante":            ["restaurant", "sushi", "pizza", "burger", "mcdonalds", "rappi", "uber eats", "pedidosya"],
    "Combustible":            ["copec", "shell", "bpgas", "petrobras", "enex", "gulf", "1click"],
    "Transporte":             ["uber", "cabify", "metro", "bip", "bolt"],
    "Farmacia":               ["farmacias ahumada", "cruz verde", "salcobrand", "farmacia"],
    "Salud":                  ["clínica", "hospital", "médico", "laboratorio", "isapre", "dentist",
                               "bice vida", "fonasa", "dental"],
    "Deporte":                ["el muro", "virtual*el muro", "gimnasio", "gym ", "sport club",
                               "fitness", "crossfit", "escalada", "running"],
    "Entretención":           ["netflix", "spotify", "disney", "hbo", "youtube", "steam", "cine", "twitch"],
    "Ropa/Calzado":           ["falabella", "ripley", "paris", "zara", "h&m", "nike", "adidas"],
    "Educación":              ["udemy", "coursera", "platzi", "colegio", "universidad", "duolingo"],
    "Servicios":              ["entel", "movistar", "claro", "vtv", "enel", "aguas", "com.mantencion"],
    "Retail":                 ["amazon", "aliexpress", "mercado libre", "sodimac", "easy"],
    "Transferencias":         ["transf.", "transf a", "transf de", "traspaso internet", "egreso por compra"],
    "Seguros":                ["cargo seguro", "seguro"],
    "Donaciones":             ["amulen"],
    "Banco/Comisiones":       ["pago cuota", "comision", "interés", "com.mant", "remuneracion"],
}

# ── Paleta de colores ──────────────────────────────────────────────────────────
C_GREEN  = "#2ecc71"
C_RED    = "#e74c3c"
C_BLUE   = "#3498db"
C_PURPLE = "#9b59b6"
C_GOLD   = "#f39c12"
C_TEAL   = "#1abc9c"
C_BG     = "#0f0f1a"
C_CARD   = "#1a1a2e"
C_BORDER = "#2d2d44"
