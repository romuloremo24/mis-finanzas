"""Pagina: Splitwise — gastos compartidos y vinculacion con transferencias."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.config import C_GREEN, C_RED, C_BLUE, C_PURPLE, C_GOLD, C_TEAL, C_CARD, C_BORDER
from utils.loaders import load_transactions
from utils.splitwise_client import (
    is_configured, get_current_user, get_groups, get_expenses,
    parse_expenses, get_balances, match_transfers,
)
from utils.ui import fmt_clp, kpi_card, apply_layout, download_csv


def render():
    st.title("🔗 Splitwise")

    if not is_configured():
        st.warning("Splitwise no esta configurado.")
        st.markdown(f"""
        <div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:10px;padding:20px;margin-top:12px">
            <h4 style="color:#fff;margin-top:0">Como configurar Splitwise</h4>
            <ol style="color:#ccc;line-height:2">
                <li>Ve a <a href="https://secure.splitwise.com/apps" target="_blank" style="color:{C_BLUE}">secure.splitwise.com/apps</a></li>
                <li>Registra una nueva aplicacion (nombre: "Mis Finanzas", callback URL: <code>http://localhost</code>)</li>
                <li>Copia tu <b>API Key</b></li>
                <li><b>Local:</b> agrega <code>SPLITWISE_API_KEY=tu_key</code> a tu archivo <code>.env</code></li>
                <li><b>Streamlit Cloud:</b> agrega en Settings → Secrets:
                    <pre style="background:#0f0f1a;padding:8px;border-radius:4px;margin-top:4px">[splitwise]
api_key = "tu_key_aqui"</pre>
                </li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
        return

    # Obtener usuario
    user = get_current_user()
    if not user:
        st.error("No se pudo conectar con Splitwise. Verifica tu API key.")
        return

    user_id = user.get("id")
    user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    st.caption(f"Conectado como **{user_name}**")

    # Selector de periodo
    df_tx = load_transactions()
    all_months = sorted(df_tx["mes"].dropna().unique(), reverse=True) if not df_tx.empty else []

    col_period, col_group = st.columns(2)
    if all_months:
        sel_month = col_period.selectbox("Periodo", all_months, index=0)
        year, month = sel_month.split("-")
        dated_after = f"{year}-{month}-01"
        if int(month) == 12:
            dated_before = f"{int(year)+1}-01-01"
        else:
            dated_before = f"{year}-{int(month)+1:02d}-01"
    else:
        sel_month = col_period.text_input("Periodo (YYYY-MM)", value=pd.Timestamp.now().strftime("%Y-%m"))
        dated_after = f"{sel_month}-01"
        dated_before = ""

    groups = get_groups()
    group_options = {"Todos los grupos": 0}
    for g in groups:
        if g.get("id") and g.get("name"):
            group_options[g["name"]] = g["id"]
    sel_group_name = col_group.selectbox("Grupo", list(group_options.keys()))
    sel_group_id = group_options[sel_group_name]

    # Obtener gastos
    raw = get_expenses(dated_after=dated_after, dated_before=dated_before,
                       group_id=sel_group_id, limit=200)
    expenses = parse_expenses(raw, user_id)

    if not expenses:
        st.info(f"Sin gastos en Splitwise para {sel_month}.")
        _render_balances()
        return

    # Resolver nombres de grupo
    group_map = {g["id"]: g["name"] for g in groups if g.get("id")}
    for e in expenses:
        e["group_name"] = group_map.get(e["group_id"], "Sin grupo")

    exp_df = pd.DataFrame(expenses)
    exp_df["date"] = pd.to_datetime(exp_df["date"])

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_gastos = exp_df["total"].sum()
    mi_total = exp_df["mi_parte"].sum()
    pague = exp_df["pagado_por_mi"].sum()
    n_expenses = len(exp_df)

    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "Total grupo", fmt_clp(total_gastos), f"{n_expenses} gastos", C_BLUE, "👥")
    kpi_card(c2, "Mi parte", fmt_clp(mi_total), f"{mi_total/total_gastos*100:.0f}% del total" if total_gastos else "", C_PURPLE, "👤")
    kpi_card(c3, "Pague yo", fmt_clp(pague), "", C_RED, "💳")
    kpi_card(c4, "Me deben", fmt_clp(pague - mi_total) if pague > mi_total else fmt_clp(0),
             f"Debo: {fmt_clp(mi_total - pague)}" if mi_total > pague else "", C_GREEN, "💰")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_gastos, tab_match, tab_balance, tab_analisis = st.tabs([
        "📋 Gastos", "🔗 Vincular Transferencias", "⚖️ Balances", "📊 Analisis"
    ])

    with tab_gastos:
        _render_expenses_table(exp_df)

    with tab_match:
        _render_transfer_matching(expenses, df_tx, sel_month)

    with tab_balance:
        _render_balances()

    with tab_analisis:
        _render_analysis(exp_df)


def _render_expenses_table(exp_df: pd.DataFrame):
    st.subheader("Gastos de Splitwise")

    disp = exp_df.copy()
    disp["fecha"] = disp["date"].dt.strftime("%d/%m/%Y")
    disp["total_fmt"] = disp["total"].apply(fmt_clp)
    disp["mi_parte_fmt"] = disp["mi_parte"].apply(fmt_clp)
    disp["pague_fmt"] = disp["pagado_por_mi"].apply(fmt_clp)

    show = disp[["fecha", "description", "category", "group_name",
                 "total_fmt", "mi_parte_fmt", "pague_fmt", "created_by"]].rename(columns={
        "fecha": "Fecha", "description": "Descripcion", "category": "Categoria",
        "group_name": "Grupo", "total_fmt": "Total", "mi_parte_fmt": "Mi parte",
        "pague_fmt": "Pague", "created_by": "Creado por",
    })
    st.dataframe(show, hide_index=True, use_container_width=True, height=400)

    download_csv(
        exp_df[["date", "description", "category", "group_name", "total",
                "mi_parte", "pagado_por_mi", "currency"]],
        f"splitwise_{exp_df['date'].min().strftime('%Y-%m') if not exp_df.empty else 'export'}.csv"
    )


def _render_transfer_matching(expenses: list[dict], df_tx, sel_month: str):
    st.subheader("Vincular transferencias con gastos Splitwise")
    st.caption(
        "Busca transferencias bancarias que correspondan a pagos en Splitwise "
        "para desglosar una transferencia en sus gastos reales."
    )

    if df_tx.empty:
        st.info("Sin transacciones bancarias para vincular.")
        return

    month_tx = df_tx[df_tx["mes"] == sel_month]
    matches = match_transfers(expenses, month_tx)

    if not matches:
        st.info("No se encontraron coincidencias automaticas entre transferencias y gastos de Splitwise.")
        st.caption("Esto puede pasar si las fechas o montos no coinciden dentro del margen de tolerancia (±3 dias, ±5%).")
        return

    st.success(f"Se encontraron **{len(matches)}** posibles vinculaciones:")

    for i, m in enumerate(matches):
        with st.expander(
            f"💳 {m['transfer_desc'][:50]} — {fmt_clp(m['transfer_monto'])} "
            f"→ {len(m['desglose'])} gastos Splitwise",
            expanded=i == 0
        ):
            c1, c2 = st.columns(2)
            c1.metric("Transferencia bancaria", fmt_clp(m["transfer_monto"]))
            c2.metric("Total Splitwise", fmt_clp(m["splitwise_total"]))

            diff = m["transfer_monto"] - m["splitwise_total"]
            if abs(diff) > 1:
                st.caption(f"Diferencia: {fmt_clp(abs(diff))} ({'sobrante' if diff > 0 else 'faltante'})")

            st.markdown("**Desglose:**")
            for d in m["desglose"]:
                col_d, col_m, col_t = st.columns([4, 2, 2])
                col_d.write(f"  {d['desc']}")
                col_m.write(f"Mi parte: {fmt_clp(d['mi_parte'])}")
                col_t.write(f"Total: {fmt_clp(d['total'])}")


def _render_balances():
    st.subheader("Balances con amigos")
    balances = get_balances()
    if not balances:
        st.info("Sin balances pendientes.")
        return

    me_deben = [b for b in balances if b["amount"] > 0]
    debo = [b for b in balances if b["amount"] < 0]

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(f"**Me deben** ({len(me_deben)})")
        for b in sorted(me_deben, key=lambda x: -x["amount"]):
            st.markdown(
                f'<div style="background:{C_CARD};border-left:3px solid {C_GREEN};'
                f'border-radius:6px;padding:8px 12px;margin:4px 0">'
                f'<b style="color:#fff">{b["friend"]}</b> '
                f'<span style="color:{C_GREEN};float:right">{fmt_clp(b["amount"])}</span></div>',
                unsafe_allow_html=True
            )

    with col_r:
        st.markdown(f"**Debo** ({len(debo)})")
        for b in sorted(debo, key=lambda x: x["amount"]):
            st.markdown(
                f'<div style="background:{C_CARD};border-left:3px solid {C_RED};'
                f'border-radius:6px;padding:8px 12px;margin:4px 0">'
                f'<b style="color:#fff">{b["friend"]}</b> '
                f'<span style="color:{C_RED};float:right">{fmt_clp(abs(b["amount"]))}</span></div>',
                unsafe_allow_html=True
            )

    total_me_deben = sum(b["amount"] for b in me_deben)
    total_debo = sum(abs(b["amount"]) for b in debo)
    neto = total_me_deben - total_debo
    st.markdown("---")
    st.metric("Balance neto", fmt_clp(neto),
              delta=f"{'A favor' if neto >= 0 else 'En contra'}")


def _render_analysis(exp_df: pd.DataFrame):
    st.subheader("Analisis de gastos compartidos")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Por categoria**")
        by_cat = exp_df.groupby("category")["mi_parte"].sum().sort_values(ascending=False)
        if not by_cat.empty:
            fig = go.Figure(go.Bar(
                x=by_cat.values, y=by_cat.index, orientation="h",
                marker=dict(color=by_cat.values, colorscale="Purples", showscale=False),
                text=[fmt_clp(v) for v in by_cat.values], textposition="outside",
            ))
            apply_layout(fig, height=max(250, len(by_cat) * 30))
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("**Por grupo**")
        by_group = exp_df.groupby("group_name")["mi_parte"].sum().sort_values(ascending=False)
        if not by_group.empty:
            fig = px.pie(values=by_group.values, names=by_group.index,
                         hole=0.45, color_discrete_sequence=px.colors.qualitative.Set2)
            apply_layout(fig, height=300,
                         legend=dict(orientation="h", y=-0.15, bgcolor="rgba(0,0,0,0)", font_color="#ccc"))
            fig.update_traces(textfont_color="#fff", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

    # Evolucion diaria
    st.markdown("**Gastos diarios (mi parte)**")
    daily = exp_df.groupby(exp_df["date"].dt.date)["mi_parte"].sum().reset_index()
    daily.columns = ["fecha", "monto"]
    if not daily.empty:
        fig = px.bar(daily, x="fecha", y="monto", color_discrete_sequence=[C_PURPLE])
        apply_layout(fig, height=250)
        st.plotly_chart(fig, use_container_width=True)
