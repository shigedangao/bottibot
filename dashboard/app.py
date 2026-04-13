# dashboard/app.py — Dashboard Streamlit interactif

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UNIVERSES, ALL_TICKERS, DASHBOARD
from data.fetcher import fetch_ohlcv, fetch_vix
from analysis.technical import compute_indicators
from main import analyze_ticker, run_screener

# ── Config Streamlit ──────────────────────────────────────────
st.set_page_config(
    page_title="📊 Stock Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS custom ────────────────────────────────────────────────
st.markdown("""
<style>
    .score-high   { color: #00c851; font-weight: bold; font-size: 1.4em; }
    .score-mid    { color: #ffbb33; font-weight: bold; font-size: 1.4em; }
    .score-low    { color: #ff4444; font-weight: bold; font-size: 1.4em; }
    .metric-card  { background: #1e2130; border-radius: 8px; padding: 12px; margin: 4px; }
    .reason-item  { font-size: 0.9em; margin: 2px 0; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Paramètres")

    universe_choice = st.selectbox(
        "Univers",
        options=["Personnalisé"] + list(UNIVERSES.keys()),
        index=0,
    )

    if universe_choice == "Personnalisé":
        custom_tickers = st.text_area(
            "Tickers (un par ligne ou séparés par virgules)",
            value="AAPL\nMSFT\nNVDA\nGOOGL\nMETA\nAMZN\nTSLA\nAVGO\nAMD",
            height=200,
        )
        tickers = [t.strip().upper() for t in custom_tickers.replace(",", "\n").split("\n") if t.strip()]
    else:
        tickers = UNIVERSES[universe_choice]
        st.info(f"{len(tickers)} actions dans cet univers")

    top_n = st.slider("Top N à afficher", min_value=5, max_value=30, value=15)

    st.divider()

    run_button = st.button("🚀 Lancer l'analyse", type="primary", use_container_width=True)

    st.divider()
    st.caption("Données via Yahoo Finance (différé 15min)")
    st.caption(f"Mis à jour : {datetime.now().strftime('%d/%m %H:%M')}")


# ── Main ──────────────────────────────────────────────────────
st.title("📊 Stock Analyzer")
st.caption("Screener technique + fondamental — aide à la décision (pas un conseil financier)")

# ── VIX Regime Banner ────────────────────────────────────────
vix_data = fetch_vix()
vix_level = vix_data["vix_level"]
vix_regime = vix_data["regime"]
if vix_level:
    regime_icons = {"CALM": "🟢", "ELEVATED": "🟠", "PANIC": "🔴"}
    regime_msgs = {
        "CALM": "Calm market — momentum strategies favored",
        "ELEVATED": "Elevated volatility — scoring shifted toward quality & fundamentals",
        "PANIC": "High volatility — scoring heavily favors quality & fundamentals",
    }
    icon = regime_icons.get(vix_regime, "⚪")
    msg = regime_msgs.get(vix_regime, "")
    if vix_regime == "PANIC":
        st.error(f"{icon} **VIX {vix_level} — {vix_regime}** — {msg}")
    elif vix_regime == "ELEVATED":
        st.warning(f"{icon} **VIX {vix_level} — {vix_regime}** — {msg}")
    else:
        st.success(f"{icon} **VIX {vix_level} — {vix_regime}** — {msg}")
else:
    vix_regime = None

# Charger les résultats existants si disponibles
results_cache = []
cache_file = "results_latest.json"
if os.path.exists(cache_file):
    try:
        with open(cache_file) as f:
            results_cache = json.load(f)
        st.info(f"📂 Dernière analyse chargée ({len(results_cache)} actions analysées)")
    except Exception:
        pass

# Lancer une nouvelle analyse
if run_button:
    with st.spinner(f"Analyse de {len(tickers)} actions en cours..."):
        progress_bar = st.progress(0)
        results_cache = []
        for i, ticker in enumerate(tickers):
            progress_bar.progress((i + 1) / len(tickers), text=f"Analyse {ticker}...")
            result = analyze_ticker(ticker, vix_regime=vix_regime)
            if result:
                results_cache.append(result)
        results_cache.sort(key=lambda x: x.get("score", 0), reverse=True)
        with open(cache_file, "w") as f:
            json.dump(results_cache, f, indent=2, default=str)
        progress_bar.empty()
    st.success(f"✅ {len(results_cache)} actions analysées avec succès !")

# Afficher les résultats
if results_cache:
    top_results = results_cache[:top_n]

    # ── Métriques globales ────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    scores = [r["score"] for r in results_cache]
    buy_signals = [r for r in results_cache if r["recommendation"] in ("FORT ACHAT", "ACHAT")]

    col1.metric("Actions analysées",    len(results_cache))
    col2.metric("Signaux d'achat",       len(buy_signals))
    col3.metric("Score moyen",           f"{sum(scores)/len(scores):.1f}/100")
    col4.metric("Meilleur score",        f"{max(scores):.1f}/100 — {results_cache[0]['ticker']}")

    st.divider()

    # ── Onglets ───────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🏆 Classement", "📈 Graphiques", "🔍 Analyse détaillée"])

    with tab1:
        # Tableau principal
        df_display = pd.DataFrame([{
            "Rang":         i + 1,
            "Ticker":       r["ticker"],
            "Nom":          r["name"][:30],
            "Secteur":      r.get("sector", "")[:20],
            "Prix":         f"{r['price']:,.2f}",
            "Score":        r["score"],
            "Signal":       f"{r['emoji']} {r['recommendation']}",
            "Mom 10j":      f"{r['momentum_10d']:+.1f}%",
            "Mom 60j":      f"{r['momentum_60d']:+.1f}%",
            "RSI":          r["rsi"],
            "EMA align.":   "✅" if r.get("ema_aligned") else "❌",
            "SL suggéré":   f"{r['stop_loss_pct']}%",
            "TP suggéré":   f"+{r['take_profit_pct']}%",
            "R/R":          f"{r['rr_ratio']}:1",
        } for i, r in enumerate(top_results)])

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%.1f"
                ),
            }
        )

        # Cards pour le top 5
        st.subheader("🌟 Top 5 — Détail")
        cols = st.columns(5)
        for i, (col, r) in enumerate(zip(cols, top_results[:5])):
            with col:
                score = r["score"]
                css_class = "score-high" if score >= 65 else ("score-mid" if score >= 50 else "score-low")
                st.markdown(f"**{r['ticker']}**")
                st.markdown(f"<span class='{css_class}'>{score:.1f}</span>", unsafe_allow_html=True)
                st.caption(f"{r['emoji']} {r['recommendation']}")
                st.caption(f"${r['price']:,.2f}")
                for reason in r.get("reasons", [])[:3]:
                    st.markdown(f"<div class='reason-item'>{reason}</div>", unsafe_allow_html=True)

    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            # Distribution des scores
            fig_hist = px.histogram(
                x=[r["score"] for r in results_cache],
                nbins=20,
                title="Distribution des scores",
                labels={"x": "Score", "y": "Nombre d'actions"},
                color_discrete_sequence=["#4f8ef7"],
            )
            fig_hist.add_vline(x=62, line_dash="dash", line_color="green", annotation_text="Achat")
            fig_hist.add_vline(x=75, line_dash="dash", line_color="lime",  annotation_text="Fort achat")
            st.plotly_chart(fig_hist, use_container_width=True)

        with col2:
            # Répartition par secteur (top actions)
            sectors = {}
            for r in top_results:
                s = r.get("sector", "Unknown")
                sectors[s] = sectors.get(s, 0) + 1
            fig_pie = px.pie(
                values=list(sectors.values()),
                names=list(sectors.keys()),
                title=f"Secteurs dans le Top {top_n}",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # Scatter Score vs Momentum 60j
        fig_scatter = px.scatter(
            x=[r["momentum_60d"] for r in results_cache],
            y=[r["score"] for r in results_cache],
            text=[r["ticker"] for r in results_cache],
            title="Score vs Momentum 60j",
            labels={"x": "Momentum 60j (%)", "y": "Score"},
            color=[r["score"] for r in results_cache],
            color_continuous_scale="RdYlGn",
        )
        fig_scatter.update_traces(textposition="top center", textfont_size=8)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with tab3:
        ticker_choice = st.selectbox(
            "Sélectionne une action",
            options=[r["ticker"] for r in top_results],
            format_func=lambda t: f"{t} — {next(r['name'] for r in top_results if r['ticker'] == t)}"
        )

        selected = next((r for r in top_results if r["ticker"] == ticker_choice), None)
        if selected:
            col1, col2 = st.columns([2, 1])

            with col1:
                # Graphique des prix avec indicateurs
                df = fetch_ohlcv(ticker_choice, period="1y")
                if df is not None:
                    df = compute_indicators(df)
                    fig = _build_price_chart(df, ticker_choice)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader(f"📋 {selected['ticker']}")
                st.metric("Score global", f"{selected['score']:.1f}/100")
                st.metric("Signal", f"{selected['emoji']} {selected['recommendation']}")

                # Décomposition du score
                st.subheader("Décomposition du score")
                detail = selected.get("score_detail", {})
                for k, v in detail.items():
                    st.progress(v / 25, text=f"{k.capitalize()}: {v:.1f}/25")

                # Raisons
                st.subheader("Analyse")
                for reason in selected.get("reasons", []):
                    st.write(reason)

                # Fondamentaux
                st.subheader("Données fondamentales")
                fund = selected.get("fundamentals_display", {})
                df_fund = pd.DataFrame(list(fund.items()), columns=["Métrique", "Valeur"])
                st.dataframe(df_fund, use_container_width=True, hide_index=True)

else:
    st.info("👆 Configure l'univers dans la sidebar et lance une analyse pour commencer.")
    st.markdown("""
    ### Comment ça marche ?
    1. **Choisis un univers** d'actions dans la sidebar
    2. **Lance l'analyse** — le screener va calculer les scores pour chaque action
    3. **Consulte le classement** — les actions sont triées par score de 0 à 100
    4. **Explore en détail** — graphiques, fondamentaux, stop-loss suggérés

    ### Méthode de scoring
    | Composante | Poids | Ce qu'on mesure |
    |---|---|---|
    | Momentum | 25% | Performance récente (10j, 60j, 120j) |
    | Tendance EMA | 25% | Structure haussière/baissière |
    | Fondamentaux | 20% | EBITDA, croissance, santé financière |
    | Qualité | 10% | Marges, ROE, profitabilité |
    | RSI | 10% | Ni suracheté ni survendu |
    | Volume | 10% | Confirmation des mouvements |
    """)


def _build_price_chart(df, ticker):
    """Construit un graphique de prix avec EMA + volume."""
    fig = go.Figure()

    # Bougies
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Prix",
    ))

    # EMAs
    fig.add_trace(go.Scatter(x=df.index, y=df["ema20"],  mode="lines",
                              line=dict(color="orange", width=1), name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=df["ema50"],  mode="lines",
                              line=dict(color="blue", width=1),   name="EMA50"))
    fig.add_trace(go.Scatter(x=df.index, y=df["ema200"], mode="lines",
                              line=dict(color="red", width=1),    name="EMA200"))

    fig.update_layout(
        title=ticker,
        xaxis_title="Date",
        yaxis_title="Prix",
        xaxis_rangeslider_visible=False,
        height=450,
    )
    return fig
