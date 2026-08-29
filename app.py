"""
Radar de Oportunidades de Negocio — Dashboard Streamlit
Lee data/latest.json generado automaticamente por GitHub Actions.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_FILE = Path(__file__).parent / "data" / "latest.json"
HISTORY_DIR = Path(__file__).parent / "data" / "history"

TREND_ICONS = {
    "creciendo": "📈",
    "spike":     "⚡",
    "estable":   "➡️",
    "declinando":"📉",
    "insuficiente": "❓",
    "nuevo":     "🆕",
}
INTENT_LABELS = {0: "—", 1: "Bajo", 2: "Medio", 3: "Alto ✨"}
INTENT_COLORS = {0: "#666", 1: "#999", 2: "#e8a820", 3: "#e84040"}

st.set_page_config(
    page_title="Radar de Oportunidades",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Carga de datos ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_data() -> dict | None:
    if not DATA_FILE.exists():
        return None
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_history_dates() -> list[str]:
    if not HISTORY_DIR.exists():
        return []
    return sorted([p.stem for p in HISTORY_DIR.glob("*.json")], reverse=True)


def load_history(date_str: str) -> dict | None:
    path = HISTORY_DIR / f"{date_str}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Radar de Oportunidades")
    st.caption("Actualizado automaticamente cada lunes y jueves")
    st.divider()

    history_dates = load_history_dates()
    if history_dates:
        selected_date = st.selectbox(
            "Ver reporte de fecha",
            options=["Ultimo"] + history_dates,
            index=0,
        )
    else:
        selected_date = "Ultimo"

    st.divider()
    if st.button("Refrescar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Cargar datos ───────────────────────────────────────────────────────────────

if selected_date == "Ultimo":
    res = load_data()
else:
    res = load_history(selected_date)

if res is None:
    st.markdown("""
    # 📡 Radar de Oportunidades

    **No hay datos todavia.**

    El primer reporte se genera automaticamente el proximo lunes o jueves via GitHub Actions.

    Para generar un reporte ahora manualmente:
    ```bash
    python generate_report.py
    ```
    """)
    st.stop()

# ── Variables ──────────────────────────────────────────────────────────────────

meta          = res.get("meta", {})
posts_all     = res.get("posts", [])
by_cat        = res.get("by_category", {})
top_cats      = res.get("top_categories", [])
trend_signals = res.get("trends", {}).get("trend_signals", {})
weekly_series = res.get("trends", {}).get("weekly_series", {})
google_trends = res.get("google_trends", {})
briefs        = res.get("briefs", {})
new_cats      = meta.get("new_categories", [])
run_at        = meta.get("run_at", "")[:10]

df = pd.DataFrame(posts_all) if posts_all else pd.DataFrame()

# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown(f"# 📡 Radar de Oportunidades")
st.caption(f"Datos del {run_at} · {meta.get('period_days', 30)} días · "
           f"{meta.get('total_posts', 0):,} posts analizados")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Ranking",
    "📈 Tendencias",
    "💡 Oportunidades",
    "🔍 Explorar",
])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — RANKING
# ════════════════════════════════════════════════════════════════════════════════

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Posts analizados", f"{meta.get('total_posts', 0):,}")
    c2.metric("Categorias detectadas", meta.get("total_categories", 0))
    c3.metric("Intencion de pago", meta.get("high_intent_count", 0))
    pct = round(meta.get("high_intent_count", 0) / max(meta.get("total_posts", 1), 1) * 100, 1)
    c4.metric("% intencion de pago", f"{pct}%")

    if new_cats:
        st.info(f"**Categorias nuevas descubiertas por Claude:** {', '.join(new_cats)}")

    st.divider()
    st.subheader("Categorias por volumen de quejas")
    st.caption("Color = porcentaje de posts con intencion de pago (amarillo → rojo)")

    rows = []
    for cat in top_cats:
        cat_posts = by_cat.get(cat, [])
        intent = sum(1 for p in cat_posts if p.get("payment_intent", 0) >= 2)
        ts = trend_signals.get(cat, {})
        signal = ts.get("signal", "insuficiente")
        rows.append({
            "Categoria": f"{TREND_ICONS.get(signal, '')} {cat}",
            "_cat": cat,
            "Quejas": len(cat_posts),
            "Intencion pago": intent,
            "% intencion": round(intent / max(len(cat_posts), 1) * 100),
            "Tendencia": signal,
            "Ratio": ts.get("ratio", 1.0),
        })

    df_rank = pd.DataFrame(rows)
    if not df_rank.empty:
        fig = px.bar(
            df_rank,
            x="Quejas",
            y="Categoria",
            orientation="h",
            color="% intencion",
            color_continuous_scale=["#1e1e2e", "#e8a820", "#e84040"],
            text="Quejas",
            hover_data={"Tendencia": True, "Intencion pago": True, "Ratio": True, "_cat": False},
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"},
            coloraxis_colorbar=dict(title="% intención<br>de pago"),
            height=max(380, len(df_rank) * 50),
            margin=dict(l=10, r=20, t=10, b=10),
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — TENDENCIAS
# ════════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Evolucion semanal por categoria")

    cats_to_show = st.multiselect(
        "Categorias",
        options=top_cats,
        default=top_cats[:5],
    )

    if cats_to_show and weekly_series:
        rows_ts = []
        for cat in cats_to_show:
            for week_str, count in sorted(weekly_series.get(cat, {}).items()):
                rows_ts.append({"Semana": week_str, "Categoria": cat, "Quejas": count})

        if rows_ts:
            df_ts = pd.DataFrame(rows_ts)
            fig_ts = px.line(
                df_ts, x="Semana", y="Quejas", color="Categoria",
                markers=True, line_shape="spline",
            )
            fig_ts.update_layout(
                height=420,
                legend=dict(orientation="h", yanchor="bottom", y=-0.4),
                margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig_ts, use_container_width=True)

    st.divider()

    # Tabla de señales de tendencia
    st.subheader("Señales de tendencia")
    st.caption("Compara el volumen de la ultima semana contra el promedio de semanas anteriores")

    signal_rows = []
    for cat in top_cats:
        ts = trend_signals.get(cat, {})
        signal = ts.get("signal", "insuficiente")
        ratio = ts.get("ratio", 1.0)
        icon = TREND_ICONS.get(signal, "")
        signal_rows.append({
            "Categoria": cat,
            "Señal": f"{icon} {signal}",
            "Ratio actual/historico": f"{ratio:.1f}x",
            "Quejas totales": len(by_cat.get(cat, [])),
        })
    st.dataframe(pd.DataFrame(signal_rows), use_container_width=True, hide_index=True)

    # Google Trends
    if google_trends:
        st.divider()
        st.subheader("Google Trends — interes de busqueda")
        for cat, records in google_trends.items():
            if not records:
                continue
            with st.expander(f"**{cat}**"):
                try:
                    df_gt = pd.DataFrame(records)
                    if "fecha" in df_gt.columns:
                        df_gt["fecha"] = pd.to_datetime(df_gt["fecha"])
                        value_cols = [c for c in df_gt.columns if c != "fecha"]
                        df_m = df_gt.melt(id_vars="fecha", value_vars=value_cols,
                                          var_name="Keyword", value_name="Interes")
                        fig_gt = px.line(df_m, x="fecha", y="Interes", color="Keyword",
                                         line_shape="spline")
                        fig_gt.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
                        st.plotly_chart(fig_gt, use_container_width=True)
                except Exception as e:
                    st.caption(f"Error mostrando Trends: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — OPORTUNIDADES
# ════════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Oportunidades de negocio detectadas")
    st.caption("Analisis generado por Claude Sonnet para las categorias con mas volumen")

    if not briefs:
        st.info("No hay briefs generados en este reporte.")
    else:
        for cat in top_cats:
            if cat not in briefs:
                continue

            cat_posts = by_cat.get(cat, [])
            intent_posts = [p for p in cat_posts if p.get("payment_intent", 0) >= 2]
            ts = trend_signals.get(cat, {})
            signal = ts.get("signal", "")
            icon = TREND_ICONS.get(signal, "")

            with st.expander(
                f"{icon} **{cat}** — {len(cat_posts)} quejas · "
                f"{len(intent_posts)} con intencion de pago",
                expanded=True,
            ):
                col_brief, col_posts = st.columns([3, 1])

                with col_brief:
                    st.markdown(briefs[cat])

                with col_posts:
                    st.markdown("**Posts con mayor intención**")
                    top_intent = sorted(intent_posts,
                                        key=lambda x: x.get("payment_intent", 0),
                                        reverse=True)[:6]
                    for p in top_intent:
                        level = p.get("payment_intent", 0)
                        color = INTENT_COLORS.get(level, "#666")
                        label = INTENT_LABELS.get(level, "")
                        title = p.get("title", "")[:65]
                        url = p.get("url", "#")
                        st.markdown(
                            f'<span style="color:{color};font-size:11px;font-weight:bold">'
                            f'[{label}]</span> '
                            f'<a href="{url}" target="_blank" style="font-size:12px">'
                            f'{title}</a>',
                            unsafe_allow_html=True,
                        )


# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — EXPLORAR
# ════════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("Explorar todos los posts clasificados")

    if df.empty:
        st.info("Sin datos.")
        st.stop()

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filter_cat = st.multiselect("Categoria", sorted(by_cat.keys()), default=[])
    with fc2:
        filter_source = st.multiselect(
            "Fuente", sorted(df["source"].unique().tolist()) if "source" in df.columns else [], default=[]
        )
    with fc3:
        filter_intent = st.selectbox(
            "Intencion de pago minima", [0, 1, 2, 3],
            format_func=lambda x: INTENT_LABELS[x]
        )

    filtered = df.copy()
    if filter_cat:
        filtered = filtered[filtered["category"].isin(filter_cat)]
    if filter_source:
        filtered = filtered[filtered["source"].isin(filter_source)]
    if "payment_intent" in filtered.columns:
        filtered = filtered[filtered["payment_intent"] >= filter_intent]

    st.caption(f"{len(filtered):,} posts")

    if not filtered.empty:
        cols = [c for c in ["category", "title", "source", "payment_intent",
                             "problem_summary", "score", "date", "url"]
                if c in filtered.columns]
        display = filtered[cols].copy()
        if "payment_intent" in display.columns:
            display["payment_intent"] = display["payment_intent"].map(INTENT_LABELS)
        display.columns = [c.replace("_", " ").title() for c in display.columns]

        sort_col = "Score" if "Score" in display.columns else display.columns[0]
        st.dataframe(
            display.sort_values(sort_col, ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar CSV",
            data=csv,
            file_name=f"radar_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
