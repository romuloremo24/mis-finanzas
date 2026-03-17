"""
Finance Dashboard — Streamlit
──────────────────────────────────────────────────────────────────────────────
Plataforma de finanzas personales: visualiza cartolas, registra gastos,
gestiona deudas, importa archivos CSV/Excel y administra categorías.

Ejecución:
  streamlit run dashboard.py
"""
import streamlit as st

from utils.config import C_BG, C_CARD, C_BORDER
from utils.loaders import load_transactions
from utils.sheets import init_sheets_tabs
from utils.ui import GLOBAL_CSS

from pages.p_dashboard       import render as page_dashboard
from pages.p_transacciones   import render as page_transacciones
from pages.p_gastos_manuales import render as page_gastos_manuales
from pages.p_deudas          import render as page_deudas
from pages.p_historico       import render as page_historico
from pages.p_analisis        import render as page_analisis
from pages.p_importar        import render as page_importar
from pages.p_categorias      import render as page_categorias


PAGES = {
    "🏠  Dashboard":             page_dashboard,
    "💳  Transacciones":          page_transacciones,
    "✏️   Gastos Manuales":       page_gastos_manuales,
    "📊  Deudas & Pendientes":    page_deudas,
    "📈  Histórico":              page_historico,
    "🤖  Análisis & Presupuesto": page_analisis,
    "📂  Importar Cartola":       page_importar,
    "🏷️   Categorías & Reglas":   page_categorias,
}


def main():
    st.set_page_config(
        page_title="Mis Finanzas",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    init_sheets_tabs()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:12px 0 20px">
            <div style="font-size:36px">💰</div>
            <div style="font-size:18px;font-weight:700;color:#fff">Mis Finanzas</div>
            <div style="font-size:11px;color:#888">Panel de control personal</div>
        </div>
        """, unsafe_allow_html=True)

        page_key = st.radio("Navegación", list(PAGES.keys()), label_visibility="collapsed")

        st.markdown("---")

        df = load_transactions()
        if not df.empty:
            last_date = df["fecha"].max()
            n_tx      = len(df)
            n_months  = df["mes"].nunique()
            st.markdown(f"""
            <div style="background:{C_CARD};border-radius:8px;padding:12px;font-size:12px;color:#aaa">
                📅 Última carga: <b style="color:#ddd">{last_date.strftime('%d/%m/%Y')}</b><br>
                📝 Transacciones: <b style="color:#ddd">{n_tx:,}</b><br>
                🗓️ Meses con datos: <b style="color:#ddd">{n_months}</b>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:{C_CARD};border-radius:8px;padding:12px;font-size:12px;color:#aaa">
                Sin datos de cartolas.<br>
                Usa <b style="color:#ddd">📂 Importar Cartola</b><br>
                o ejecuta <code>python main.py</code>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄  Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── Render página activa ──────────────────────────────────────────────────
    PAGES[page_key]()


if __name__ == "__main__":
    main()
