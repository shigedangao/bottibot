# Stock Analyzer

> [!NOTE]
> The goal of this project is to evaluate the performance of a whole vibe coded project w/o doing any manual modification and only give guidance on the theme of stock, crypto or else... (It seems that everyone tries to do that with Claude). All of the code is and will be generated with Mr Claude.

Smart stock screener — technical + fundamental analysis, with VIX regime adaptation, sector-relative scoring, and a backtesting engine.
Decision support for Degiro or any other broker. **Not financial advice.**

---

## Installation

```bash
# 1. Clone the repo
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
uv run python main.py --universe ASIA_LARGE
uv run python main.py --universe SEMICONDUCTORS
uv run python main.py --universe PHARMA_BIOTECH
uv run python main.py --universe GROWTH_TECH

# Analyze specific tickers
uv run python main.py --tickers AAPL MSFT NVDA TSLA

# Control the number of results
uv run python main.py --top 20

# Cap sector concentration (e.g. max 3 stocks per sector)
uv run python main.py --universe US_LARGE --max-per-sector 3
```

### Backtest the strategy

```bash
# Default: US_LARGE, 24 months, top 5, vs SPY
uv run python backtest.py

# Custom run
uv run python backtest.py --universe GROWTH_TECH --months 24 --top 5
uv run python backtest.py --universe ASIA_LARGE --months 12 --top 3
uv run python backtest.py --tickers AAPL NVDA MSFT GOOGL AMZN --months 36 --top 3
```

Outputs: monthly period returns, total return, CAGR, alpha vs SPY, Sharpe, max drawdown, win rate.

### Dashboard mode (web interface)

```bash
uv run streamlit run dashboard/app.py
```

Opens http://localhost:8501 in your browser.

### Telegram morning digest

Push a daily digest (top N, score movers vs yesterday, new BUY signals, drop-outs, upcoming earnings) to a Telegram chat.

**Setup (one-time):**
1. Create a bot via [@BotFather](https://t.me/BotFather) → save the **bot token**
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Open a chat with your new bot and send `/start` (required — Telegram blocks outbound until you initiate)
4. Create a `.env` file at the project root:
   ```
   TELEGRAM_BOT_TOKEN=123456:AAAA...
   TELEGRAM_CHAT_ID=123456789
   ```

**Usage:**

```bash
# Sanity check the credentials
uv run python -m bot.telegram --test

# Send today's digest
uv run python -m bot.telegram --universe US_LARGE --top 5

# Dry-run (prints to stdout, no Telegram push)
uv run python -m bot.digest --universe US_LARGE --top 5
```

Daily snapshots are written to `.snapshots/results_YYYY-MM-DD.json` so the next morning's digest can diff scores and signals against the previous run.

---

## Structure

```
bottibot/
├── config.py              # Universes, scoring weights, sector benchmarks, VIX regime
├── main.py                # CLI screener
├── backtest.py            # Monthly-rebalance backtest vs SPY
├── pyproject.toml         # Dependencies (managed by uv)
├── data/
│   └── fetcher.py         # Yahoo Finance — OHLCV, fundamentals, VIX, earnings
├── analysis/
│   ├── technical.py       # EMA, RSI, MACD, ATR, ADX, momentum, relative strength
│   └── fundamental.py     # Sector-relative fundamental scoring
├── scoring/
│   └── engine.py          # Composite scoring engine, VIX-adjusted weights
├── bot/
│   ├── digest.py          # Morning digest logic (diff vs previous snapshot)
│   ├── formatting.py      # Telegram MarkdownV2 formatter
│   ├── storage.py         # Daily snapshot persistence
│   └── telegram.py        # One-way Telegram sender
└── dashboard/
    └── app.py             # Streamlit dashboard
```

---

## Scoring method

| Component   | Weight | What it measures                                                              |
|-------------|--------|-------------------------------------------------------------------------------|
| Momentum    | 25%    | Absolute momentum (60%) blended with relative strength vs SPY (40%)           |
| Trend       | 25%    | EMA20 > EMA50 > EMA200 alignment, MACD confirmation                           |
| Fundamental | 20%    | Quality / growth / value / health, **scored relative to sector benchmark**    |
| Quality     | 10%    | Gross margin, operating margin, ROE vs sector norm                            |
| RSI         | 10%    | Neither overbought (>70) nor oversold (<35)                                   |
| Volume      | 10%    | Volume ratio vs 20-day average                                                |

### Signal interpretation

| Score    | Signal      | Meaning                                       |
|----------|-------------|-----------------------------------------------|
| 75-100   | STRONG BUY  | All signals aligned, high conviction          |
| 62-75    | BUY         | Mostly positive signals                       |
| 50-62    | NEUTRAL     | Mixed signals, wait                           |
| 38-50    | CAUTION     | Negative signals, high risk                   |
| 0-38     | AVOID       | Downtrend, do not buy                         |

---

## Key features

### VIX regime adaptation
The screener fetches `^VIX` once per run and classifies the market:
- **CALM** (VIX < 20) — base weights, momentum-friendly
- **ELEVATED** (VIX 20–30) — shifts weight from momentum to quality & fundamentals
- **PANIC** (VIX > 30) — heavy shift toward defensive metrics

Displayed as a banner in both CLI and dashboard.

### Sector-relative scoring
A 20% gross margin is excellent for a bank but weak for a SaaS company. `SECTOR_BENCHMARKS` in `config.py` holds reference values per sector (Technology, Healthcare, Financial Services, etc.), and each stock's fundamentals are scored against its own peer group.

### Relative strength vs SPY
Separates alpha from beta by comparing each stock's 10/20/60-day returns against SPY. A stock up +30% while SPY is up +25% only gets a small excess-return boost.

### Earnings calendar warning
Detects upcoming earnings within 7 days (`⚡` marker in the results table) so you can avoid opening positions right before a report.

### Sector concentration cap
Pass `--max-per-sector N` to enforce diversification and prevent the top N being dominated by a single sector.

### Backtesting
`backtest.py` runs a monthly rebalance: each month it scores all tickers using data available at that point, buys the top-N equally, holds one month, rebalances. Compares portfolio vs SPY buy-and-hold. Reports CAGR, alpha, Sharpe, max drawdown, win rate.

> Technical-only backtest (fundamentals are excluded to avoid look-ahead bias, since yfinance does not reliably provide historical fundamentals).

---

## Customization

Everything is in `config.py`:

- **Add stocks**: edit `UNIVERSES`
- **Change weights**: edit `SCORING_WEIGHTS`
- **Adjust thresholds**: edit `FUNDAMENTAL` and `TECHNICAL`
- **Tune sector benchmarks**: edit `SECTOR_BENCHMARKS`
- **Tune VIX regime thresholds & weight adjustments**: edit `VIX`

---

## Limitations

- Yahoo Finance data: ~15 minute delay, sometimes incomplete for EU/Asia stocks
- Fundamentals are only published quarterly/annually
- Backtest has **survivorship bias** (universe uses current tickers only)
- Backtest has **no transaction costs modeled** — real-world fees/slippage will reduce alpha
- **This tool helps filter and prioritize — it does not replace your judgment**
- Always check recent news before buying (earnings, scandals, acquisitions...)

---

## Roadmap

- [ ] Run longer backtests (36–60 months) across multiple universes to stress-test the edge
- [ ] Email/Telegram alerts when a score exceeds a threshold
- [ ] Score history (tracking changes over time)
- [ ] Transaction cost modeling in the backtest
- [ ] Sentiment score (news, Reddit)
- [ ] Crypto trading bot (Binance spot, paper trading first)
