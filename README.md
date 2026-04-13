# Stock Analyzer

> [!NOTE]
> The goal of this project is to evaluate the performance of a whole vibe coded project w/o doing any manual modification and only give guidance on the theme of stock, crypto or else... (It seems that everyone tries to do that with Claude). All of the code is and will be generated with Mr Claude. 

Smart stock screener — technical + fundamental analysis.
Decision support for Degiro or any other broker. **Not financial advice.**

---

## Installation

```bash
# 1. Clone / copy the folder
cd bottibot

# 2. Install dependencies (requires uv — https://docs.astral.sh/uv/)
uv sync
```

---

## Usage

### Terminal mode (quick screener)

```bash
# Analyze all configured stocks
uv run python main.py

# Analyze a specific universe
uv run python main.py --universe US_LARGE
uv run python main.py --universe EU_LARGE
uv run python main.py --universe GROWTH_TECH

# Analyze specific tickers
uv run python main.py --tickers AAPL MSFT NVDA TSLA

# Control the number of results
uv run python main.py --top 20
```

### Dashboard mode (web interface)

```bash
uv run streamlit run dashboard/app.py
```

Opens http://localhost:8501 in your browser.

---

## Structure

```
bottibot/
├── config.py              # Central configuration (universes, weights, thresholds)
├── main.py                # Main script + terminal display
├── pyproject.toml         # Dependencies (managed by uv)
├── data/
│   └── fetcher.py         # Yahoo Finance data fetching (OHLCV + fundamentals)
├── analysis/
│   ├── technical.py       # Technical indicators (EMA, RSI, MACD, ADX...)
│   └── fundamental.py     # Fundamental analysis (margins, growth, balance sheet)
├── scoring/
│   └── engine.py          # Composite scoring engine (0-100)
└── dashboard/
    └── app.py             # Interactive Streamlit dashboard
```

---

## Scoring method

| Component   | Weight | What it measures                          |
|-------------|--------|-------------------------------------------|
| Momentum    | 25%    | 10d / 60d / 120d performance              |
| Trend       | 25%    | EMA20 > EMA50 > EMA200 alignment          |
| Fundamental | 20%    | EBITDA, revenue growth, balance sheet      |
| Quality     | 10%    | Gross margins, ROE, profitability          |
| RSI         | 10%    | Neither overbought (>70) nor oversold (<35)|
| Volume      | 10%    | Volume confirmation                       |

### Interpretation

| Score    | Signal          | Meaning                                    |
|----------|-----------------|--------------------------------------------|
| 75-100   | STRONG BUY      | All signals aligned, high conviction       |
| 62-75    | BUY             | Mostly positive signals                    |
| 50-62    | NEUTRAL         | Mixed signals, wait                        |
| 38-50    | CAUTION         | Negative signals, high risk                |
| 0-38     | AVOID           | Downtrend, do not buy                      |

---

## Customization

Everything is in `config.py`:

- **Add stocks**: edit `UNIVERSES`
- **Change weights**: edit `SCORING_WEIGHTS`
- **Adjust thresholds**: edit `FUNDAMENTAL` and `TECHNICAL`

---

## Limitations

- Yahoo Finance data: ~15 minute delay, sometimes incomplete for EU stocks
- Fundamentals are only published quarterly/annually
- **This tool helps filter and prioritize — it does not replace your judgment**
- Always check recent news before buying (earnings, scandals, acquisitions...)

---

## Roadmap

- [ ] Email/Telegram alerts when a score exceeds a threshold
- [ ] Score history (tracking changes over time)
- [ ] Earnings calendar integration (avoid buying before publications)
- [ ] Sentiment score (news, Reddit, Twitter)
- [ ] Backtest the selection strategy
