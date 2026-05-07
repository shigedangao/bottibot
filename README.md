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
# Default: US_LARGE, 36 months, top 5, with 15 bps/side transaction cost
uv run python backtest.py

# Custom run
uv run python backtest.py --universe GROWTH_TECH --months 36 --top 5
uv run python backtest.py --universe ASIA_LARGE --months 24 --top 3
uv run python backtest.py --tickers AAPL NVDA MSFT GOOGL AMZN --months 60 --top 3

# Multi-universe sweep (compare alpha across universes)
uv run python backtest.py --sweep                                  # default 4 universes
uv run python backtest.py --sweep US_LARGE EU_LARGE SEMICONDUCTORS # explicit list
uv run python backtest.py --sweep --months 60 --cost-bps 20        # longer + higher cost

# Stress-test with higher cost assumptions (small caps, illiquid markets)
uv run python backtest.py --universe SMALL_MID --cost-bps 30
```

**Outputs**: per-period returns with turnover, gross vs net CAGR, **alpha gross & alpha net** (after costs), Sharpe (net), max drawdown, win rate vs SPY, average monthly turnover, total cost drag, and a **Deploy?** verdict (`STRONG` / `OK` / `WEAK` / `NO`) summarizing the historical edge. Sweep mode shows the verdict as a column for quick comparison across universes.

#### Deploy? verdict

A mechanical multi-criteria readout — **not financial advice**. Computed from the backtest result alone:

| Verdict | Net alpha | Sharpe | Win rate | Max drawdown |
|---------|-----------|--------|----------|--------------|
| `STRONG` | ≥ 5% | ≥ 0.70 | ≥ 45% | ≥ -40% |
| `OK`     | ≥ 2% | ≥ 0.50 | ≥ 40% | ≥ -50% |
| `WEAK`   | > 0  | (fails OK criteria above) |
| `NO`     | ≤ 0  | — | — | — |

Tunable via `BACKTEST["deploy_thresholds"]` in `config.py`. The verdict scores each universe in isolation — a universe can pass `STRONG` while the strategy as a whole still fails to generalize across other universes, so always read it alongside the sweep.

#### Transaction cost model

Each rebalance charges `cost_per_side_bps` (default **15 bps** = 5 bps fee + 10 bps slippage, realistic for liquid US large-caps via Degiro/IBKR) on the **changed fraction** of the portfolio:

- Period 0: 100% × cost_per_side (initial buy from cash)
- Subsequent: `2 × turnover_fraction × cost_per_side` (round-trip on rotated names)

Tune via `--cost-bps` or `BACKTEST["cost_per_side_bps"]` in `config.py`. Bump to 25-40 bps for small-caps or international markets where slippage is wider.

> **Why this matters**: a strategy with 50%+ monthly turnover at 15 bps/side incurs ~2-3% annual drag. Apparent alpha that doesn't survive that cost isn't real edge — it's noise that you'd pay your broker to capture.

#### Stickiness (turnover throttle)

Currently-held positions get a configurable score bonus (`BACKTEST["stickiness_bonus_pts"]`, default **5.0**) when the rebalance sort runs, so a challenger must beat a held name by more than that gap to displace it. `0` reproduces pure top-N every month; higher values hold positions longer.

Tune via `--stickiness`. In our 60-month sweep, raising stickiness from 0 → 5 cut average turnover from 67–79%/mo down to 55–64%/mo and lifted net alpha by **+5–7 pp** on the universes where the strategy has edge (SEMICONDUCTORS, US_LARGE) — most of the gain came from capturing momentum continuation, not just cost savings. On universes without edge (EU_LARGE, GROWTH_TECH) it made results slightly worse: holding losers longer hurts when the underlying score has no signal.

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

## Deploy on GCP (Cloud Run)

The same Docker image powers two Cloud Run targets:

- **Cloud Run Service** — Streamlit dashboard (long-running HTTP)
- **Cloud Run Job** — daily Telegram digest (cron-triggered via Cloud Scheduler)

Snapshots are persisted to **Google Cloud Storage** so the digest job can diff against yesterday and the dashboard can read the morning's pre-computed results.

### One-time setup

```bash
# Replace with your values
export PROJECT_ID=your-gcp-project
export REGION=europe-west1
export BUCKET=bottibot-snapshots-${PROJECT_ID}
export REPO=bottibot
export IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/bottibot:latest

# Enable APIs
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com \
    storage.googleapis.com --project=${PROJECT_ID}

# Artifact Registry repo
gcloud artifacts repositories create ${REPO} --repository-format=docker \
    --location=${REGION} --project=${PROJECT_ID}

# GCS bucket for snapshots
gcloud storage buckets create gs://${BUCKET} --location=${REGION} --project=${PROJECT_ID}

# Telegram secrets
echo -n "$TELEGRAM_BOT_TOKEN" | gcloud secrets create telegram-bot-token --data-file=- --project=${PROJECT_ID}
echo -n "$TELEGRAM_CHAT_ID"   | gcloud secrets create telegram-chat-id   --data-file=- --project=${PROJECT_ID}
```

### Build & push the image

Build locally with Docker, tag it for Artifact Registry, then push.

```bash
# One-time: let Docker authenticate to Artifact Registry in this region
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Build, tag, push
docker build -t bottibot:latest .
docker tag bottibot:latest ${IMAGE}
docker push ${IMAGE}
```

> If you're on Apple Silicon, add `--platform=linux/amd64` to `docker build` — Cloud Run runs `linux/amd64` and won't start an `arm64` image.

### Deploy the dashboard (Cloud Run Service)

```bash
gcloud run deploy bottibot-dashboard \
    --image=${IMAGE} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --allow-unauthenticated \
    --memory=1Gi \
    --concurrency=10 \
    --min-instances=0 \
    --max-instances=2 \
    --set-env-vars=BOTTIBOT_STORAGE_BACKEND=gcs,BOTTIBOT_GCS_BUCKET=${BUCKET}
```

> Drop `--allow-unauthenticated` if you'd rather keep the dashboard private (auth via IAM).

### Deploy the digest (Cloud Run Job + Scheduler)

```bash
gcloud run jobs create bottibot-digest \
    --image=${IMAGE} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --memory=1Gi \
    --task-timeout=600 \
    --set-env-vars=BOTTIBOT_STORAGE_BACKEND=gcs,BOTTIBOT_GCS_BUCKET=${BUCKET} \
    --set-secrets=TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,TELEGRAM_CHAT_ID=telegram-chat-id:latest \
    --command=uv \
    --args=run,python,-m,bot.telegram,--universe,US_LARGE,--top,5

# Trigger daily at 07:00 Europe/Paris
gcloud scheduler jobs create http bottibot-digest-daily \
    --location=${REGION} \
    --project=${PROJECT_ID} \
    --schedule="0 7 * * *" \
    --time-zone="Europe/Paris" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/bottibot-digest:run" \
    --http-method=POST \
    --oauth-service-account-email="$(gcloud iam service-accounts list --filter='displayName:Compute Engine default service account' --format='value(email)' --project=${PROJECT_ID})"
```

### Storage backend env vars

The same code paths run locally and on GCP — only the env vars change:

| Variable                       | Default              | Purpose                                              |
|--------------------------------|----------------------|------------------------------------------------------|
| `BOTTIBOT_STORAGE_BACKEND`     | `local`              | Set to `gcs` to persist to Cloud Storage             |
| `BOTTIBOT_GCS_BUCKET`          | _(required for gcs)_ | GCS bucket name                                      |
| `BOTTIBOT_GCS_PREFIX`          | `bottibot`           | Object name prefix inside the bucket                 |
| `BOTTIBOT_SNAPSHOT_DIR`        | `.snapshots`         | Local backend only — directory for daily snapshots   |
| `BOTTIBOT_LATEST_PATH`         | `results_latest.json`| Local backend only — path to the dashboard cache     |

### Run the container locally

```bash
# Dashboard
docker build -t bottibot .
docker run --rm -p 8080:8080 -e PORT=8080 bottibot

# Digest (uses your local .env)
docker run --rm --env-file .env bottibot \
    uv run python -m bot.telegram --universe US_LARGE --top 5
```

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
│   ├── fundamental.py     # Sector-relative fundamental scoring
│   └── potential.py       # Emerging potential badge (forward-looking signals)
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

### Emerging potential badge (🌱)
Forward-looking tag — **separate from the 0-100 score** — flagging companies that may be the next ASML / NVDA before the market fully prices it in. Awarded when at least 2 of these signals fire together:

1. **Forward earnings step-up** — analysts expect a meaningful earnings jump (forward P/E ≪ trailing P/E, or trailing missing/negative)
2. **Growth not yet priced in** — strong revenue growth (≥20%) but flat/weak 60d price action
3. **Attractive PEG with growth** — PEG < 1.5 combined with ≥15% revenue growth
4. **Heavy R&D investment** — R&D / revenue above sector norm (the ASML pre-EUV pattern)

Tag shows as `🌱` next to the ticker in the CLI and the dashboard. Tunable via `EMERGING_POTENTIAL` in `config.py`.

> Intentionally noisy — for every ASML there are 100 misses. Use as a discretionary watchlist, not a buy signal.

### Sector concentration cap
Pass `--max-per-sector N` to enforce diversification and prevent the top N being dominated by a single sector.

### Backtesting
`backtest.py` runs a monthly rebalance: each month it scores all tickers using data available at that point, buys the top-N equally, holds one month, rebalances. Compares portfolio vs SPY buy-and-hold. Reports gross/net CAGR, alpha (gross and net of costs), Sharpe, max drawdown, win rate, and average turnover. `--sweep` compares alpha across multiple universes in one run.

> Technical-only backtest (fundamentals are excluded to avoid look-ahead bias, since yfinance does not reliably provide historical fundamentals). Includes a configurable transaction cost model (commissions + slippage) — see the [Backtest section](#backtest-the-strategy) above.

---

## Customization

Everything is in `config.py`:

- **Add stocks**: edit `UNIVERSES`
- **Change weights**: edit `SCORING_WEIGHTS`
- **Adjust thresholds**: edit `FUNDAMENTAL` and `TECHNICAL`
- **Tune sector benchmarks**: edit `SECTOR_BENCHMARKS`
- **Tune VIX regime thresholds & weight adjustments**: edit `VIX`
- **Tune emerging potential thresholds**: edit `EMERGING_POTENTIAL` (R&D intensity by sector, forward step-up ratio, PEG cap, etc.)
- **Tune backtest costs & defaults**: edit `BACKTEST` (`cost_per_side_bps`, default lookback, sweep universes)

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

- [x] Transaction cost modeling in the backtest (commissions + slippage, applied to actual turnover)
- [x] Multi-universe sweep to stress-test edge across markets
- [x] Stickiness threshold to throttle turnover and capture continuation
- [ ] Run longer backtests (60+ months) and document the results in this repo
- [ ] Email/Telegram alerts when a score exceeds a threshold
- [ ] Score history (tracking changes over time)
- [ ] Sentiment score (news, Reddit)
- [ ] Crypto trading bot (Binance spot, paper trading first)
