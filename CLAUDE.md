# bottibot — Claude Code Context

## Project
Stock Analyzer + future Crypto Trading Bot. Python-based, dependency-managed via `uv`.

## Current state

Full **Stock Analyzer** architecture:

```
bottibot/
├── config.py              # Universes, scoring weights, sector benchmarks, VIX regime config
├── main.py                # CLI screener with Rich (ranking + top-3 detail)
├── backtest.py            # Monthly-rebalance backtest vs SPY benchmark
├── pyproject.toml         # Dependencies (managed by uv)
├── data/fetcher.py        # Yahoo Finance — OHLCV, fundamentals, VIX, benchmark, earnings
├── analysis/
│   ├── technical.py       # EMA, RSI, MACD, Bollinger, ATR, ADX, momentum, relative strength vs SPY
│   └── fundamental.py     # Sector-relative scoring (margin, ROE, P/E, growth, balance sheet)
├── scoring/engine.py      # Composite 0-100 score, VIX-adjusted weights, ATR-based SL/TP
└── dashboard/app.py       # Streamlit: ranking, charts, VIX regime banner, detail view
```

## Scoring method

| Component   | Weight | Logic |
|-------------|--------|-------|
| Momentum    | 25%    | Absolute momentum (60%) + relative strength vs SPY (40%), 10d/20d/60d/120d weighted |
| Trend       | 25%    | EMA20 > EMA50 > EMA200, +5% bonus if aligned & MACD bullish |
| Fundamental | 20%    | Quality×0.35 + Growth×0.30 + Value×0.20 + Health×0.15, scored relative to sector benchmarks |
| Quality     | 10%    | Gross margin, operating margin, ROE — all vs sector norm |
| RSI         | 10%    | <35 oversold=0.8, >70 overbought=0.2, otherwise linear |
| Volume      | 10%    | volume / volume_avg_20d, capped at 1.0 for ratio ≥ 2 |

Score → Signal: 75+ STRONG BUY · 62+ BUY · 50+ NEUTRAL · 38+ CAUTION · <38 AVOID

Stop-loss = -1.5×ATR% · Take-profit = SL × (3.0 if score≥75, 2.0 if ≥62, 1.5 otherwise)

## VIX regime adaptation

Weights shift based on market volatility (one `^VIX` fetch per screener run):
- **CALM** (VIX < 20): base weights (momentum-friendly)
- **ELEVATED** (VIX 20–30): -7% momentum, -3% trend, +5% fundamental, +5% quality
- **PANIC** (VIX > 30): -12% momentum, -5% trend, +8% fundamental, +7% quality

## Sector-relative fundamentals

`SECTOR_BENCHMARKS` in `config.py` holds reference margins/ROE/P/E per sector. Each stock's fundamental metrics are scored against its own sector, so a SaaS 80% margin and a bank 20% margin are both evaluated correctly.

## Backtesting

`backtest.py` runs monthly rebalance: each month it scores all tickers using only data available up to that date, buys top-N equally, holds for one month, measures returns vs SPY. Reports CAGR, alpha, Sharpe, max drawdown, win rate. Technical-only (fundamentals excluded to avoid look-ahead bias).

## Stack
- Python 3.14 via uv, yfinance, pandas, numpy, Streamlit, Plotly, Rich

## Roadmap
1. Run backtests across more universes and longer windows (24–60 months) to validate the edge
2. Telegram/email alerts when score crosses a threshold
3. Crypto Trading Bot (Binance API, paper trading → real with small capital)
   - Strategy: Mean reversion in ranging markets, momentum in trending
   - Spot only, no leverage

## Conventions
- All thresholds/weights in `config.py` — no magic numbers in code
- Scores 0.0–1.0 inside modules, ×100 only in `scoring/engine.py`
- Silent errors per ticker — a single failure never breaks a batch
- All user-facing output in English (ticker names, signals, reasons, tables)

## Useful commands
```bash
uv run python main.py --tickers AAPL NVDA MSFT ASML.AS MC.PA
uv run python main.py --universe EU_LARGE --top 20
uv run python main.py --universe US_LARGE --max-per-sector 3
uv run python backtest.py --universe US_LARGE --months 24 --top 5
uv run streamlit run dashboard/app.py
```
