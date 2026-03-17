"""Helpers de UI: formatters, CSS global, componentes de chart."""
import streamlit as st

from .config import C_BG, C_CARD, C_BORDER

# ─── Formatters ───────────────────────────────────────────────────────────────

def fmt_clp(v: float) -> str:
    return f"${v:,.0f}"

def fmt_usd(v: float) -> str:
    return f"US${v:,.2f}"

def fmt_amount(v: float, moneda: str = "CLP") -> str:
    return fmt_clp(v) if moneda == "CLP" else fmt_usd(v)

def delta_str(current: float, previous: float) -> str:
    if previous == 0:
        return ""
    pct = (current - previous) / abs(previous) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}% vs mes anterior"


# ─── Componente KPI card ──────────────────────────────────────────────────────

def kpi_card(col, label: str, value: str, sub: str = "", color: str = "#3498db", icon: str = ""):
    col.markdown(f"""
    <div style="background:{C_CARD};border-radius:12px;padding:18px 20px;
                border-left:4px solid {color};height:100px;">
        <div style="color:#888;font-size:11px;text-transform:uppercase;
                    letter-spacing:1.2px;margin-bottom:4px">{icon} {label}</div>
        <div style="color:#fff;font-size:22px;font-weight:700;line-height:1.2">{value}</div>
        <div style="color:{'#2ecc71' if sub.startswith('+') else '#e74c3c' if sub.startswith('-') else '#888'};
                    font-size:11px;margin-top:4px">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# ─── CSS global ───────────────────────────────────────────────────────────────

GLOBAL_CSS = f"""
<style>
    .stApp {{ background-color: {C_BG}; color: #e0e0e0; }}
    section[data-testid="stSidebar"] {{ background-color: {C_CARD}; border-right: 1px solid {C_BORDER}; }}
    .stButton > button {{ border-radius: 8px; border: 1px solid {C_BORDER}; background: {C_CARD}; color: #fff; }}
    .stButton > button:hover {{ background: {C_BORDER}; border-color: #555; }}
    .stDataFrame {{ border-radius: 8px; }}
    div[data-testid="stMetric"] label {{ color: #888 !important; }}
    h1 {{ color: #fff !important; margin-bottom: 0.5rem !important; }}
    h2, h3 {{ color: #ddd !important; }}
    .stTabs [data-baseweb="tab"] {{ color: #aaa; }}
    .stTabs [aria-selected="true"] {{ color: #fff !important; }}
    .stAlert {{ border-radius: 8px; }}
    .block-container {{ padding-top: 1.5rem; }}
    hr {{ border-color: {C_BORDER}; }}
</style>
"""

# ─── Chart layout ─────────────────────────────────────────────────────────────

CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#ccc",
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", font_color="#ccc"),
    xaxis=dict(gridcolor="#2d2d44", zerolinecolor="#2d2d44"),
    yaxis=dict(gridcolor="#2d2d44", zerolinecolor="#2d2d44"),
)

def apply_layout(fig, **extra):
    fig.update_layout(**{**CHART_LAYOUT, **extra})
    return fig


# ─── Download button helper ───────────────────────────────────────────────────

def download_csv(df, filename: str, label: str = "⬇️ Exportar CSV"):
    """Renderiza un botón de descarga CSV."""
    csv = df.to_csv(index=False).encode("utf-8-sig")  # utf-8-sig para Excel en Windows
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")
