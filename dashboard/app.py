# dashboard/app.py — Dashboard Streamlit interactif

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UNIVERSES, ALL_TICKERS, DASHBOARD
from data.fetcher import fetch_ohlcv, fetch_vix
from analysis.technical import compute_indicators
from main import analyze_ticker, run_screener
from bot.storage import load_latest, save_latest, score_history_for_ticker


FUNDAMENTAL_DEFINITIONS = {
    "Name":             "Company legal name.",
    "Sector":           "GICS sector classification.",
    "Market Cap":       "Total share value = price × outstanding shares.",
    "P/E":              "Price / trailing 12-month earnings. Lower = cheaper vs current profits; negative or N/A means losses.",
    "PEG":              "P/E divided by earnings growth rate. <1 = priced low for its growth, >3 = expensive even after growth.",
    "P/B":              "Price / book value. <1 = trading below net assets, >3 = significant premium to book.",
    "Gross Margin":     "(Revenue − COGS) / Revenue. Pricing power and product economics.",
    "EBITDA Margin":    "EBITDA / Revenue. Profitability before financing & tax — useful for cross-country comparisons.",
    "Operating Margin": "Operating income / Revenue. Profit from core operations after running costs.",
    "ROE":              "Return on Equity = Net income / Shareholder equity. How efficiently equity capital generates profit.",
    "Revenue Growth":   "Year-over-year change in revenue. Top-line momentum.",
    "Earnings Growth":  "Year-over-year change in earnings. Bottom-line momentum.",
    "D/E":              "Debt / Equity. Financial leverage; >100% means debt exceeds equity.",
    "Current Ratio":    "Short-term assets / short-term liabilities. >1 = can cover near-term obligations.",
    "Quality Score":    "Aggregated profitability score (gross/operating margin, ROE) vs sector benchmark.",
    "Growth Score":     "Aggregated growth score (revenue + earnings) vs sector expectations.",
    "Value Score":      "Aggregated valuation score (P/E, PEG) vs sector — lower P/E gets a better score.",
    "Health Score":     "Aggregated balance-sheet score (D/E, current ratio, free cash flow).",
}


def _build_score_history_chart(history: list[dict], ticker: str):
    """Line chart of score over time with signal-threshold reference lines."""
    fig = go.Figure()

    dates  = [h["date"]  for h in history]
    scores = [h["score"] for h in history]

    fig.add_trace(go.Scatter(
        x=dates, y=scores, mode="lines+markers",
        name="Score",
        line=dict(color="#4f8ef7", width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>Score: %{y:.1f}<extra></extra>",
    ))

    # Signal threshold reference lines
    fig.add_hline(y=75, line_dash="dash", line_color="#00c851",
                  annotation_text="STRONG BUY", annotation_position="right")
    fig.add_hline(y=62, line_dash="dash", line_color="#5cb85c",
                  annotation_text="BUY", annotation_position="right")
    fig.add_hline(y=50, line_dash="dot",  line_color="gray",
                  annotation_text="NEUTRAL", annotation_position="right")
    fig.add_hline(y=38, line_dash="dot",  line_color="#ffbb33",
                  annotation_text="CAUTION", annotation_position="right")

    fig.update_layout(
        title=f"{ticker} — Score history",
        xaxis_title="Date",
        yaxis_title="Score",
        yaxis=dict(range=[0, 100]),
        height=320,
        margin=dict(l=40, r=80, t=40, b=40),
    )
    return fig


def _build_price_chart(df, ticker):
    """Build a candlestick price chart with EMA overlays."""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price",
    ))

    fig.add_trace(go.Scatter(x=df.index, y=df["ema20"],  mode="lines",
                              line=dict(color="orange", width=1), name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=df["ema50"],  mode="lines",
                              line=dict(color="blue", width=1),   name="EMA50"))
    fig.add_trace(go.Scatter(x=df.index, y=df["ema200"], mode="lines",
                              line=dict(color="red", width=1),    name="EMA200"))

    fig.update_layout(
        title=ticker,
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=450,
    )
    return fig


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
    st.title("⚙️ Settings")

    universe_choice = st.selectbox(
        "Universe",
        options=["Custom"] + list(UNIVERSES.keys()),
        index=0,
    )

    if universe_choice == "Custom":
        custom_tickers = st.text_area(
            "Tickers (one per line or comma-separated)",
            value="AAPL\nMSFT\nNVDA\nGOOGL\nMETA\nAMZN\nTSLA\nAVGO\nAMD",
            height=200,
        )
        tickers = [t.strip().upper() for t in custom_tickers.replace(",", "\n").split("\n") if t.strip()]
    else:
        tickers = UNIVERSES[universe_choice]
        st.info(f"{len(tickers)} stocks in this universe")

    top_n = st.slider("Top N to display", min_value=5, max_value=30, value=15)

    st.divider()

    run_button = st.button("🚀 Run analysis", type="primary", use_container_width=True)

    st.divider()
    st.caption("Data via Yahoo Finance (15-min delayed)")
    st.caption(f"Updated: {datetime.now().strftime('%d/%m %H:%M')}")


# ── Main ──────────────────────────────────────────────────────
st.title("📊 Stock Analyzer")
st.caption("Technical + fundamental screener — decision support (not financial advice)")

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

# Load cached results if available (local FS or GCS)
results_cache = load_latest() or []
if results_cache:
    st.info(f"📂 Loaded last analysis ({len(results_cache)} stocks)")

# Run a fresh analysis
if run_button:
    concurrency = 5
    with st.spinner(f"Analyzing {len(tickers)} stocks (concurrency={concurrency})..."):
        progress_bar = st.progress(0)
        results_cache = []
        completed = 0

        def _analyze(ticker):
            try:
                return analyze_ticker(ticker, vix_regime=vix_regime)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(_analyze, t): t for t in tickers}
            for future in as_completed(futures):
                ticker = futures[future]
                completed += 1
                progress_bar.progress(completed / len(tickers), text=f"Analyzed {ticker} ({completed}/{len(tickers)})")
                result = future.result()
                if result:
                    results_cache.append(result)

        results_cache.sort(key=lambda x: x.get("score", 0), reverse=True)
        save_latest(results_cache)
        progress_bar.empty()
    st.success(f"✅ {len(results_cache)} stocks analyzed successfully!")

# Display results
if results_cache:
    top_results = results_cache[:top_n]

    # ── Global metrics ────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    scores = [r["score"] for r in results_cache]
    buy_signals = [r for r in results_cache if r["recommendation"] in ("STRONG BUY", "BUY")]

    col1.metric("Stocks analyzed", len(results_cache))
    col2.metric("Buy signals",     len(buy_signals))
    col3.metric("Average score",   f"{sum(scores)/len(scores):.1f}/100")
    col4.metric("Best score",      f"{max(scores):.1f}/100 — {results_cache[0]['ticker']}")

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🏆 Ranking", "📈 Charts", "🔍 Detailed analysis"])

    with tab1:
        # Main table
        df_display = pd.DataFrame([{
            "Rank":       i + 1,
            "Ticker":     r["ticker"],
            "Name":       r["name"][:30],
            "Sector":     r.get("sector", "")[:20],
            "Price":      f"{r['price']:,.2f}",
            "Score":      r["score"],
            "Signal":     f"{r['emoji']} {r['recommendation']}",
            "Potential":  "🌱" if r.get("emerging_potential") else "",
            "Mom 10d":    f"{r['momentum_10d']:+.1f}%",
            "Mom 60d":    f"{r['momentum_60d']:+.1f}%",
            "RSI":        r["rsi"],
            "EMA align.": "✅" if r.get("ema_aligned") else "❌",
            "SL":         f"{r['stop_loss_pct']}%",
            "TP":         f"+{r['take_profit_pct']}%",
            "R/R":        f"{r['rr_ratio']}:1",
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

        # Cards for the top 5
        st.subheader("🌟 Top 5 — Detail")
        cols = st.columns(5)
        for i, (col, r) in enumerate(zip(cols, top_results[:5])):
            with col:
                score = r["score"]
                css_class = "score-high" if score >= 65 else ("score-mid" if score >= 50 else "score-low")
                badge = " 🌱" if r.get("emerging_potential") else ""
                st.markdown(f"**{r['ticker']}{badge}**")
                st.markdown(f"<span class='{css_class}'>{score:.1f}</span>", unsafe_allow_html=True)
                st.caption(f"{r['emoji']} {r['recommendation']}")
                st.caption(f"${r['price']:,.2f}")
                for reason in r.get("reasons", [])[:3]:
                    st.markdown(f"<div class='reason-item'>{reason}</div>", unsafe_allow_html=True)

        # Emerging potential candidates section
        emerging = [r for r in top_results if r.get("emerging_potential")]
        if emerging:
            st.subheader("🌱 Emerging potential")
            st.caption("Forward-looking tag — not part of the score. Worth a closer look.")
            for r in emerging:
                with st.expander(f"{r['ticker']} — {r['name'][:40]}"):
                    for sig in r.get("emerging_signal_reasons", []):
                        st.markdown(f"- {sig}")
                    rd = r.get("rd_intensity")
                    if rd is not None:
                        st.caption(f"R&D / revenue: {rd*100:.1f}%")

    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            # Score distribution
            fig_hist = px.histogram(
                x=[r["score"] for r in results_cache],
                nbins=20,
                title="Score distribution",
                labels={"x": "Score", "y": "Number of stocks"},
                color_discrete_sequence=["#4f8ef7"],
            )
            fig_hist.add_vline(x=62, line_dash="dash", line_color="green", annotation_text="Buy")
            fig_hist.add_vline(x=75, line_dash="dash", line_color="lime",  annotation_text="Strong Buy")
            st.plotly_chart(fig_hist, use_container_width=True)

        with col2:
            # Sector breakdown of top stocks
            sectors = {}
            for r in top_results:
                s = r.get("sector", "Unknown")
                sectors[s] = sectors.get(s, 0) + 1
            fig_pie = px.pie(
                values=list(sectors.values()),
                names=list(sectors.keys()),
                title=f"Sectors in the Top {top_n}",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # Score vs 60d momentum scatter
        fig_scatter = px.scatter(
            x=[r["momentum_60d"] for r in results_cache],
            y=[r["score"] for r in results_cache],
            text=[r["ticker"] for r in results_cache],
            title="Score vs 60d Momentum",
            labels={"x": "60d Momentum (%)", "y": "Score"},
            color=[r["score"] for r in results_cache],
            color_continuous_scale="RdYlGn",
        )
        fig_scatter.update_traces(textposition="top center", textfont_size=8)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with tab3:
        ticker_choice = st.selectbox(
            "Select a stock",
            options=[r["ticker"] for r in top_results],
            format_func=lambda t: f"{t} — {next(r['name'] for r in top_results if r['ticker'] == t)}"
        )

        selected = next((r for r in top_results if r["ticker"] == ticker_choice), None)
        if selected:
            col1, col2 = st.columns([2, 1])

            with col1:
                # Price chart with indicators
                df = fetch_ohlcv(ticker_choice, period="1y")
                if df is not None:
                    df = compute_indicators(df)
                    fig = _build_price_chart(df, ticker_choice)
                    st.plotly_chart(fig, use_container_width=True)

                # Score history (from saved daily snapshots)
                history = score_history_for_ticker(ticker_choice)
                if len(history) >= 2:
                    fig_hist = _build_score_history_chart(history, ticker_choice)
                    st.plotly_chart(fig_hist, use_container_width=True)
                else:
                    st.caption(
                        "📈 *Score history will appear here once you've saved a few daily snapshots* "
                        "(automatically generated each time the digest or screener runs)."
                    )

            with col2:
                st.subheader(f"📋 {selected['ticker']}")
                st.metric("Overall score", f"{selected['score']:.1f}/100")
                st.metric("Signal", f"{selected['emoji']} {selected['recommendation']}")

                if selected.get("emerging_potential"):
                    st.success("🌱 **Emerging potential**")
                    for sig in selected.get("emerging_signal_reasons", []):
                        st.markdown(f"- {sig}")

                # Score breakdown
                st.subheader("Score breakdown")
                detail = selected.get("score_detail", {})
                for k, v in detail.items():
                    st.progress(v / 25, text=f"{k.capitalize()}: {v:.1f}/25")

                # Analysis reasons
                st.subheader("Analysis")
                for reason in selected.get("reasons", []):
                    st.write(reason)

                # Fundamentals
                st.subheader("Fundamental data")
                fund = selected.get("fundamentals_display", {})
                df_fund = pd.DataFrame([
                    {
                        "Metric":     k,
                        "Value":      v,
                        "Definition": FUNDAMENTAL_DEFINITIONS.get(k, ""),
                    }
                    for k, v in fund.items()
                ])
                st.dataframe(
                    df_fund,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Definition": st.column_config.TextColumn(width="large"),
                    },
                )

else:
    st.info("👆 Pick a universe in the sidebar and run an analysis to get started.")
    st.markdown("""
    ### How it works
    1. **Pick a universe** in the sidebar
    2. **Run the analysis** — the screener computes a score for each stock
    3. **Read the ranking** — stocks sorted by score from 0 to 100
    4. **Drill in** — charts, fundamentals, suggested stop-loss

    ### Scoring method
    | Component | Weight | What it measures |
    |---|---|---|
    | Momentum | 25% | Recent performance (10d, 60d, 120d) |
    | EMA trend | 25% | Bullish / bearish structure |
    | Fundamentals | 20% | EBITDA, growth, financial health |
    | Quality | 10% | Margins, ROE, profitability |
    | RSI | 10% | Neither overbought nor oversold |
    | Volume | 10% | Confirms the move |
    """)
