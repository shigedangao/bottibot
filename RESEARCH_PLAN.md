# Quant Research Plan — bottibot

Iterative roadmap for evolving the stock analyzer from a hand-picked composite score into a measurable, factor-driven research framework.

Update this document as phases are completed; append findings to the **Status log** at the bottom.

## Why this plan exists

The current scoring engine (`scoring/engine.py`) combines six components with hand-picked weights:

| Component | Weight |
|---|---|
| Momentum | 25% |
| Trend | 25% |
| Fundamental | 20% |
| Quality | 10% |
| RSI | 10% |
| Volume | 10% |

From a quant-research lens this has known weaknesses:

- **Factor redundancy** — Momentum + Trend + RSI all derive from price; ~60% of the score is one bet in three costumes.
- **Hand-picked weights** — No empirical justification. VIX regime adjustments are also unvalidated.
- **Absolute scoring** — Stocks scored against fixed thresholds rather than ranked cross-sectionally within universe.
- **No risk model** — Top-N equal-weight ignores covariance (top-5 in semis = one semi bet, not five).
- **Backtest fragility** — Single Sharpe number, no penalty for the many iterations we'll run while developing.

The plan replaces the methodology in phases, with measurement infrastructure (Phase 0) coming first so every later change can be judged honestly.

## Defaults locked in

User trusted the plan; these are the defaults for the open design questions:

- **Starting point** — Phase 0 (IC harness + cross-sectional ranking). Without it, every later change is unmeasurable.
- **Data scope** — Hybrid. Keep Yahoo Finance for prices/OHLCV. Fundamentals remain current-snapshot, explicitly excluded from backtest. Document the limitation, don't source point-in-time data yet.
- **Strategy scope** — Long-only screener (current product). Optional later: surface bottom-decile as "avoid/short candidates" without actually shorting in the backtest.

---

## Phase 0 — Research infrastructure

Goal: build the measurement scaffolding so every later change can be judged honestly.

### 0.1 Information Coefficient (IC) harness
- New module: `analysis/ic.py`.
- For any signal series and a forward-return horizon (1m, 3m), compute Spearman rank correlation per period.
- Aggregate into IC mean, IC std, IR (= mean / std × √periods), hit rate.
- Slice by: month, year, universe, sector.
- Initial smoke test: run on current `score` output to establish a baseline IC we'll try to beat.

### 0.2 Cross-sectional ranking
- Wrap per-stock score outputs with a universe-relative rank (z-score or percentile).
- Additive change: existing absolute thresholds stay for now.
- Decide later (Phase 2): should signal → rank happen before combination, after, or both?

### 0.3 Backtest statistical rigor
- Add bootstrap confidence intervals around CAGR / Sharpe / alpha in `backtest.py`.
- Implement Deflated Sharpe Ratio (Bailey & López de Prado 2014). Track the number of variants tested.
- Target output format: `Sharpe = 0.8 [0.4, 1.2] 95% CI, DSR = 0.6` rather than a bare number.

### 0.4 Document data limitations
- Add a "Known limitations" section to `CLAUDE.md` (or a `LIMITATIONS.md`):
  - Survivorship bias — Yahoo gives current constituents only.
  - No point-in-time fundamentals.
  - Look-ahead in `SECTOR_BENCHMARKS` (calibrated on today's data).
- Not a fix; just makes the constraint explicit so we don't oversell results.

---

## Phase 1 — Replace factors with academically-tested ones

One factor at a time, with the Phase 0 IC harness measuring impact at each step.

### 1.1 Momentum: 12-1 (cheap quick win)
- Replace current weighted blend with 12-month return **skipping the last month** (short-term reversal effect).
- Keep current as `momentum_legacy` to compare.
- Validate: 12-1 IC > current momentum IC on our universes?

### 1.2 Momentum: residual (Blitz/Huij/Martens 2011)
- Regress each stock's monthly returns on Fama-French 3-factor (or just market β as a simpler start), take residuals.
- Rank by residual returns over the 12-1 window.
- Expected: ~2× risk-adjusted return vs raw momentum, lower drawdowns, less sector concentration.

### 1.3 Quality: gross profitability + Piotroski
- Add **gross profitability** (Novy-Marx 2013): gross profits / total assets.
- Add **Piotroski F-Score**: 9 binary indicators across profitability / leverage / efficiency.
- Combine into Quality composite (QMJ-inspired): equal-weighted z-scores of {gross profitability, F-Score, ROE}.
- Existing margins/ROE become inputs to this composite, not a standalone factor.

### 1.4 Value: EV/EBIT
- Replace P/E with **EV/EBIT** (fall back to EV/Sales when EBIT is negative).
- More robust to capital structure and one-offs than P/E.

### 1.5 Optional: Betting-Against-Beta
- Rolling 1-year beta vs SPY.
- Low-beta tilt as either a separate factor or a risk overlay.
- Defer if Phase 1.1–1.4 already gives clean improvement.

---

## Phase 2 — Combine factors honestly

### 2.1 IC-weighted combination
- For each factor, use rolling IC (trailing 12 months) to weight its contribution to the composite.
- Floor weights at 0 — never short a factor whose IC has been negative for a year.
- Compare against equal-weight and against current hand-picked weights.

### 2.2 Sector and beta neutralization
- At each rebalance, demean each signal by sector before ranking.
- Optionally regress out beta exposure.
- Goal: prevent "momentum" from being covertly "long whichever sector ran".

### 2.3 Cross-universe validation
- Re-run `--sweep` across all major universes.
- Report per-universe IC and Sharpe.
- A factor that works in only 1 of 5 universes is suspect.

---

## Phase 3 — Risk-aware sizing & costs

### 3.1 Inverse-volatility weighting
- Replace equal-weight top-N with weights ∝ 1 / σ.
- Cheap, well-known variance reduction.

### 3.2 Turnover penalty
- Formalize the existing stickiness threshold as an explicit transaction-cost penalty in the rank.
- New entrants pay an expected-cost discount before competing for portfolio slots.

### 3.3 Re-validate after costs
- Phase 1+2 results must hold net of realistic costs (current model: 15 bps/side).
- If not, factor design needs revisiting.

---

## Reading list

Open-access PDFs.

| Paper | Year | Authors | Relevance |
|---|---|---|---|
| [Gross profitability premium](https://mysimon.rochester.edu/novy-marx/research/OSoV.pdf) | 2013 | Novy-Marx | Quality factor (gross profits / assets) |
| [Quality Minus Junk](http://www.econ.yale.edu/~shiller/behfin/2013_04-10/asness-frazzini-pedersen.pdf) | 2019 | Asness, Frazzini, Pedersen | Quality composite construction |
| [Residual Momentum](https://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf) | 2011 | Blitz, Huij, Martens | Better momentum |
| [Piotroski F-Score](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf) | 2000 | Piotroski | 9-point fundamental quality |
| [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | 2014 | Bailey, López de Prado | Backtest validity |
| […and the Cross-Section of Expected Returns](https://www.nber.org/system/files/working_papers/w20592/w20592.pdf) | 2016 | Harvey, Liu, Zhu | t-stat ≥ 3 hurdle for new factors |

## Human resources

- **Emmanuel Gobet** (Sorbonne Université) — Monte Carlo, stochastic calculus, numerical finance. Strong potential reviewer for Phase 0 (validation infrastructure / bootstrap design / multiple-testing corrections). Less aligned with Phase 1–2 factor design (that's the AQR/Novy-Marx world).

## Open questions for future sessions

- IC computed monthly vs daily — likely monthly, confirm when implementing.
- Per-stock weight cap (separate from sector cap) — needed?
- Benchmark beyond SPY for non-US universes?
- Does the existing `--sweep` already produce the cross-universe data Phase 2 needs, or do we need new aggregation?
- Does any of this validation work transfer to the eventual crypto bot in `CLAUDE.md` roadmap?

---

## Status log

- **2026-05-10** — Plan drafted.
- **2026-05-10** — Phase 0.1 done. Built `analysis/ic.py` (pure Spearman IC + aggregate stats) and `ic.py` CLI (per-rebalance score loop, 1-month forward returns, supports `--signal {composite,momentum,rel_strength,trend,rsi,volume,…}` to test components individually). Established baseline on **US_LARGE, 60 months**:

  | Signal       | Mean IC | IR (annualized) | Hit rate | t-stat |
  |--------------|--------:|----------------:|---------:|-------:|
  | composite    | -0.0003 |           -0.00 |      46% |  -0.01 |
  | momentum     | ~+0.018 |           +0.25 |      56% |  +0.55 |
  | rel_strength | ~+0.010 |           +0.14 |      47% |  +0.31 |
  | trend        | ~+0.010 |           +0.14 |      54% |  +0.30 |
  | rsi          | ~+0.009 |           +0.13 |      53% |  +0.29 |
  | volume       | ~-0.015 |           -0.21 |      49% |  -0.47 |

  **Findings:**
  - No signal clears t-stat ≥ 2.0, let alone the ≥ 3.0 bar Harvey/Liu/Zhu argue for. Everything is within sampling noise over 60 months on US_LARGE.
  - Momentum is the strongest individual component (IR +0.25), but still well below the "useful" threshold of 0.5.
  - Volume is mildly anti-predictive (IR -0.21). Confirms it should not be a standalone weighted component.
  - The composite (IR ≈ 0) is **weaker than its strongest individual component (momentum, IR +0.25)** — combining several near-zero signals at fixed weights washes out the small edge that exists. Concrete evidence for the "factor redundancy + hand-picked weights" critique that motivated this plan.
  - The 24-month run gave a +0.035 mean IC and IR +0.48 — illusory. t-stat was only +0.66 (not significant). Future tests should default to ≥60 months.
  - Important caveat: 60 months on a 40-stock universe is still low statistical power for monthly IC.

- **2026-05-10** — Phase 1.1 done. Replaced `momentum_score` formula with a config-switched version (`TECHNICAL["momentum_definition"]`, defaults to `"12_1"`). Legacy 10/20/60/120 blend still reachable via `"legacy"`. Added `momentum_12`, `momentum_12_1`, `momentum_6_1` to `compute_indicators` / `get_technical_signals` / `ic.py SIGNAL_FNS`.

  **IC comparison (60m, IR, all four universes):**

  | Signal           | US_LARGE | EU_LARGE | GROWTH_TECH | SEMIS | All-positive? |
  |------------------|---------:|---------:|------------:|------:|:-------------:|
  | momentum (legacy) |    +0.25 |    -0.32 |       -0.09 | -0.26 |    1/4        |
  | momentum_12_1    |    +0.48 |    +0.22 |       +0.36 | +0.27 |   **4/4**     |
  | momentum_12      |   **+0.61** | +0.19 |       +0.30 | +0.10 |    4/4        |
  | momentum_6_1     |    +0.24 |        — |           — |     — |    —          |

  **Composite (full score) IC after promotion: 1/4 → 3/4 universes positive, EU still slightly negative.**

  **Backtest comparison (60m, top-5, alpha net of 15bps/side):**

  | Universe       | Legacy   | 12_1     | 12       |
  |----------------|---------:|---------:|---------:|
  | SEMICONDUCTORS | +22.9% (OK)     | +27.9% (STRONG) | +27% (STRONG)   |
  | US_LARGE       | +12.0% (STRONG) | **-0.1% (NO)**  | +6.5% (STRONG)  |
  | EU_LARGE       | -12.7%   | -12.8%   | -12%     |
  | GROWTH_TECH    | -16.6%   | -17.9%   | -16%     |

  **The IC and backtest disagree on US_LARGE.** IC says 12_1 > legacy (+0.48 vs +0.25 IR); backtest says legacy > 12_1 (+12% vs -0.1% alpha). Likely explanation: IC measures rank correlation across all 40 stocks; top-5 selection only cares about the right tail. Legacy's heavy weight on the most recent month happened to align with US large-cap momentum continuation 2020–2025 (NVDA, META, etc.) — captured the right tail, missed elsewhere.

  **Choice rationale for "12_1" default:**
  - Cross-universe IC is unambiguous: 4/4 positive vs 1/4 for legacy. Robustness > peak.
  - Matches the academic standard (Jegadeesh-Titman 1993, Carhart 1997, Asness et al.). Defensible.
  - Legacy's US_LARGE backtest win is concentrated in one regime; argues against generalization.
  - Reversibility is cheap: `TECHNICAL["momentum_definition"] = "legacy"` to flip back.
  - Open question deferred to Phase 2.x: IC harness should add quintile/decile-spread metrics so we can measure *right-tail* predictive power, not just full-cross-section IC. That's where the real divergence lives.

  **Persistent failures:** EU_LARGE and GROWTH_TECH still produce negative alpha regardless of momentum definition. The bottleneck isn't momentum — it's that the strategy doesn't generalize beyond US momentum-friendly large caps. Phase 2 (sector neutralization, IC-weighted combination) and Phase 1.3+ (better quality/value factors) needed before these universes will work.

- **2026-05-10** — Phase 0.x extension: added quintile-spread metric to the IC harness (`quintile_spread`, `spread_summary` in `analysis/ic.py`; printed alongside IC in `ic.py`). Resolves the "IC vs backtest disagree" puzzle from Phase 1.1 — IC measures full-cross-section rank correlation, but a top-N portfolio only cares whether the right tail outperforms the left tail.

  **Quintile spread head-to-head (annualized, top 20% − bottom 20%, 60m):**

  | Signal           | US_LARGE | SEMIS  | EU_LARGE | GROWTH_TECH | Average |
  |------------------|---------:|-------:|---------:|------------:|--------:|
  | momentum_legacy  |    +6.8% |  -4.0% |    -6.9% |      -11.5% |  -3.9%  |
  | momentum_12_1    |   +12.6% | +25.1% |    +8.5% |       +1.7% | +12.0%  |
  | momentum_12      |   +18.1% | +18.6% |    +7.7% |       +1.3% | +11.4%  |

  **Three findings that update the picture:**
  1. **Legacy was even worse than full-IC suggested** — quintile spread is negative in 3/4 universes (only US barely positive at +6.8%). The earlier impression that "legacy won the US backtest" was a top-5 concentration effect (top-5 of 40 = 12.5% of names, narrower than the top quintile = 20%); the regime-specific concentration noise faded once we looked at quintile granularity. IC was right; the backtest was misleading.
  2. **12-1 and 12 both dominate legacy by ~16 pp/yr on average.** Either is a clear upgrade.
  3. **12-1 vs 12 is now a close race.** Choice depends on which universe weight matters most. Sticking with 12-1: matches the academic standard and wins on average.

  **Methodology note:** quintile spread is now the primary metric for evaluating long-only factors going forward. Spearman IC + IR remains useful for "does the signal predict?" but quintile spread answers the more relevant "does the signal separate the right tail from the left tail?" — which is what top-N selection consumes.

  **Reading list update:** future Phase 1 work should report all three: Spearman IC, IR, quintile-spread t-stat. The harness does this in one pass.

- **2026-05-10** — Phase 1.2 done. Residual momentum 12-1 (Blitz/Huij/Martens 2011) implemented in `analysis/technical.py:_compute_residual_momentum_12_1` — resamples to monthly, OLS regresses stock returns on benchmark over a 36-month window, returns sum of residuals over months t-12..t-1 in percent. Wired into `signals["residual_momentum_12_1"]`, exposed in `ic.py SIGNAL_FNS`, promoted to production via `TECHNICAL["momentum_definition"] = "residual_12_1"`.

  **Residual vs raw 12-1 momentum (annualized quintile spread, 60m):**

  | Universe       | Raw 12-1 | Residual 12-1 | Δ          |
  |----------------|---------:|--------------:|-----------:|
  | US_LARGE       |   +12.6% |          +9.3% | -3.3 pp   |
  | SEMIS          |   +25.1% |         +23.6% | -1.5 pp   |
  | EU_LARGE       |    +8.5% |         +15.8% | **+7.3 pp** |
  | GROWTH_TECH    |    +1.7% |         +17.8% | **+16.1 pp** |
  | **Average**    | **+12.0%** |     **+16.6%** | **+4.6 pp** |

  Residual delivers the literature claim: dramatic improvement on the sector-concentrated baskets (GROWTH_TECH IR jumps from +0.36 to +0.89, t-IC +1.98 — basically at the t≥2 bar for the first time), modest cost on diverse mega-cap baskets where market-beta noise was already small.

  **Phase 1.2 also exposed the bigger problem: composite dilution.**

  When residual_12_1 is run *as the only signal* via the IC harness, it produces strong cross-universe results (4/4 positive IR, avg spread +16.6%). But when run as the *momentum component* of the existing 25/25/10/10 composite, the result collapses on GROWTH_TECH:

  | Universe       | residual_12_1 alone | Composite (residual + trend + rsi + volume) |
  |----------------|--------------------:|---------------------------------------------:|
  | SEMIS          |              +23.6% |                                       +28.8% |
  | EU_LARGE       |              +15.8% |                                        +9.3% |
  | US_LARGE       |               +9.3% |                                        +3.9% |
  | GROWTH_TECH    |              +17.8% |                                       **-12.0%** |

  The non-momentum components (trend IR +0.14 ≈ 0, RSI IR +0.13 ≈ 0, volume IR **-0.21** = anti-predictive) drag the composite below what momentum alone would deliver. Volume is the worst offender — it's actively destructive and currently weighted 10%.

  **Backtest with residual_12_1 in production (60m sweep):**

  | Universe       | Legacy alpha | 12_1 alpha | Residual alpha |
  |----------------|-------------:|-----------:|---------------:|
  | SEMIS          |       +22.9% |     +27.9% |         +25.0% |
  | US_LARGE       |       +12.0% |      -0.1% |          **+9.6%** |
  | EU_LARGE       |       -12.7% |     -12.8% |         -12.7% |
  | GROWTH_TECH    |       -16.6% |     -17.9% |         -17.4% |

  US_LARGE alpha recovered +10pp vs raw 12_1. EU and GROWTH stay broken in backtest because composite dilution kills them despite the strong underlying signal. **The backtest disagreement is now fully explained: not the momentum definition, the composite formula.**

  **Implication for plan ordering:** Phase 2.1 (IC-weighted combination) should jump ahead of further Phase 1 factor additions. Every new factor we add will be diluted by the same noise sources unless we fix the combination first. Quality (1.3) and EV/EBIT (1.4) work would be wasted otherwise.

- **2026-05-10** — Phase 2.1 done. Replaced hand-picked weights with IC-derived weights. New `config.py` introduces `SCORING_WEIGHTS_FIXED` (original) and `SCORING_WEIGHTS_IC` (active default); `_get_adjusted_weights` floors at 0 so VIX adjustments can't push a near-zero weight negative.

  **Cross-universe IRs measured (60m sweep, used to derive weights):**

  | Signal               | US_LARGE | EU_LARGE | GROWTH | SEMIS  | Avg IR |
  |----------------------|---------:|---------:|-------:|-------:|-------:|
  | residual momentum    |    +0.46 |    +0.59 |  +0.89 |  +0.13 |  +0.52 |
  | rsi                  |    +0.13 |    -0.01 |  +0.24 |  +0.20 |  +0.14 |
  | volume               |    -0.21 |    +0.22 |  +0.08 |  +0.37 |  +0.12 |
  | trend                |    +0.14 |    -0.23 |  +0.05 |  -0.10 |  -0.04 |

  **Surprise:** trend was the worst offender, not volume. Trend is destructive on average across universes (largely redundant with momentum). RSI is mildly positive across 3/4. Volume is mixed but average-positive.

  **New weights** (avg IR floored at 0, renormalized within original 0.70 technical budget; fundamental/quality unchanged):

  | Signal       | Old weight | New weight |
  |--------------|-----------:|-----------:|
  | momentum     |       0.25 |       0.47 |
  | trend        |       0.25 |       **0.00** |
  | rsi          |       0.10 |       0.13 |
  | volume       |       0.10 |       0.10 |
  | fundamental  |       0.20 |       0.20 |
  | quality      |       0.10 |       0.10 |

  **Composite IC sweep (after IC weights + residual momentum):**

  | Universe       | IR before | IR after | Spread before | Spread after |
  |----------------|----------:|---------:|--------------:|-------------:|
  | US_LARGE       |     +0.19 |  **+0.51** |         +3.9% |       +13.9% |
  | EU_LARGE       |     +0.13 |  **+0.45** |         +9.3% |       +14.2% |
  | GROWTH_TECH    |     +0.21 |    +0.30 |        -12.0% |        -7.6% |
  | SEMIS          |     +0.05 |    +0.09 |        +28.8% |       +23.2% |

  US_LARGE and EU_LARGE both clear the +0.5 "useful" IR threshold (US for the first time on the composite).

  **Backtest sweep (IC weights + residual momentum, 60m, top-5):**

  | Universe       | Phase 1.1 alpha | Phase 1.2 alpha | Phase 2.1 alpha | Sharpe |
  |----------------|----------------:|----------------:|----------------:|-------:|
  | SEMIS          |          +27.9% |          +25.0% |      **+35.0%** |   1.10 |
  | US_LARGE       |           -0.1% |           +9.6% |      **+20.6%** |   1.30 |
  | EU_LARGE       |          -12.8% |          -12.7% |           -3.5% |   0.70 |
  | GROWTH_TECH    |          -17.9% |          -17.4% |          -15.7% |   0.09 |

  **2 of 4 universes now STRONG verdict.** US_LARGE went from "broken" to "Sharpe 1.30, +20% alpha". Turnover dropped from ~55%/mo to ~40%/mo because IC-weighted weights produce more stable rankings (less churn from noise components).

  **Persistent failures:** EU_LARGE alpha improved by 9pp but still negative; GROWTH_TECH barely moved. GROWTH_TECH quintile spread still negative (-7.6%) — momentum alone isn't enough; needs the quality / value factors of Phase 1.3-1.4. EU_LARGE quintile spread is positive (+14.2%) but top-5 concentration eats it; this might benefit from a wider top-N or sector neutralization (Phase 2.2).

  **Recommended next step:** Phase 1.3 (Quality — gross profitability + Piotroski F-Score). The hypothesis: GROWTH_TECH stocks differ enormously on profitability quality, so a quality factor should sort them well. Worth measuring before assuming the universe is unworkable.

- **2026-05-10** — Phase 1.5 (Betting-Against-Beta) tested. **Negative result.** Implemented `_compute_beta` in `analysis/technical.py` (rolling 36-month beta of monthly stock returns regressed on benchmark monthly returns), exposed `signals["beta_36m"]`, added `bab` (= -beta) and `beta_36m` to `ic.py SIGNAL_FNS`.

  **BAB IC sweep (60m, 4 universes):**

  | Universe       |    IR | Spread (ann) | t-stat |
  |----------------|------:|-------------:|-------:|
  | GROWTH_TECH    | +0.09 |        +7.0% |  +0.48 |
  | EU_LARGE       | -0.10 |        -2.9% |  -0.36 |
  | SEMIS          | -0.27 |       -18.7% |  -1.75 |
  | US_LARGE       | -0.13 |       -24.9% |  -1.76 |
  | **Average**    | **-0.10** |   **-10%** |        |

  **Anti-predictive in 3/4 universes.** Opposite the Frazzini-Pedersen 2014 literature claim. Likely explanations:
  - **Regime mismatch**: 2020-2025 was a tech-led momentum bull market — exactly the regime where high-beta crushes low-beta. BAB historically wins in deleveraging events and bear markets.
  - **Universe size mismatch**: BAB was validated on broad CRSP (~3000 stocks). Our universes are 35-40 mega-caps where beta is a weak differentiator.
  - **Survivorship**: high-beta names that died are absent from our current-snapshot universes — biases beta-based factor against itself.

  **Decision: not promoting BAB to the composite.** Would hurt 3/4 universes. Code stays (pure-price, near-free to compute) so we can re-test in different regimes or expanded universes. `beta_36m` itself is useful as a diagnostic.

  **Lesson:** academic factor literature is sample-dependent. Validation in our specific data is non-negotiable. BAB worked 1926–2012 across thousands of stocks; in our 2020–2025 mega-cap window it's the wrong sign.

- **2026-05-10** — Phase 0.3 done. Statistical hygiene added. New `analysis/stats.py` with `bootstrap_ci`, `bootstrap_pairs_ci`, `deflated_sharpe_ratio` (Bailey & López de Prado 2014 — Probabilistic Sharpe Ratio + multi-test correction). Wired into `backtest.py` output: 95% CIs on CAGR/Sharpe/alpha, plus PSR(0) and DSR with `BACKTEST["n_trials_for_dsr"]` (default 20).

  **Sweep readout (Phase 2.1 setup, 60m, top-5, N=20 for DSR):**

  | Universe       |   Alpha | Alpha 95% CI            | Sharpe | DSR  |
  |----------------|--------:|:------------------------|-------:|-----:|
  | SEMICONDUCTORS |  +35.7% | [-0.2%, +92.3%]         |   1.10 |  47% |
  | US_LARGE       |  +20.0% | [+0.5%, +43.3%]         |   1.30 |  67% |
  | EU_LARGE       |   -3.5% | [-21.3%, +13.1%]        |   0.70 |  18% |
  | GROWTH_TECH    |  -15.2% | [-31.2%, +9.2%]         |   0.09 |   1% |

  US_LARGE PSR(0) = 99.9% (single-test, Sharpe is bulletproof > 0). After correcting for 20 trials the Sharpe threshold rises to 1.11 (annualized), and our observed 1.30 only beats it by 0.19 — DSR 67%, **below the 95% confidence bar but well above coin-flip**. Real edge, fragile measurement.

  **Key honest readings:**
  1. **US_LARGE is our strongest result, real but not bulletproof.** Alpha CI lower bound is +0.5% — barely positive at 95% confidence. Sharpe CI [+0.49, +2.15] confirms positive Sharpe is plausible but the band is wide.
  2. **SEMIS alpha looks impressive but CI is enormous.** [-0.2%, +92.3%] — single high-vol universe with concentrated picks. DSR 47% is essentially a coin flip on whether this is real after multi-test.
  3. **EU_LARGE and GROWTH_TECH DSRs (18%, 1%)** confirm the persistent failures aren't "unlucky regime" — there genuinely isn't edge in our setup.
  4. **Skew +0.65 on US_LARGE returns** is a positive sign (right tail) — winning months bigger than losing ones.

  **What we now know honestly:**
  - We have edge in US_LARGE, with reasonable confidence (DSR 67%).
  - Likely edge in SEMIS, with low confidence (DSR 47%).
  - No measurable edge in EU_LARGE or GROWTH_TECH.
  - Future variant testing should increment `n_trials_for_dsr` to keep DSR honest.

  **Implication for next steps:** the strategy is "publishable in a research note, not deployable at scale yet." Concrete next things that would raise DSR confidence:
  - Out-of-sample test: 2010-2020 or longer windows where we can.
  - Broader universe: add S&P 500 or MSCI World — variance reduction from more names.
  - Point-in-time fundamentals — required to test Phase 1.3 (quality) without look-ahead.
  - Stop iterating on technical factors until we can do these. More variants = lower DSR.

- **2026-06-12** — Emerging universes + 🌱 badge validation. Added three curated smaller-cap universes (`TECH_EMERGING`, `SEMIS_EMERGING`, `PHARMA_EMERGING`), a liquidity filter (`LIQUIDITY` / `avg_dollar_volume`, $5M/day floor — flows into screener + digest), and a small-cap cost preset (`--cost-preset small_cap` = 30 bps/side).

  **60-month backtest at realistic 30 bps cost (top 5):** only **1/3** beat SPY net — SEMIS_EMERGING (+18.6% alpha) but its alpha 95% CI is **[-15.1%, +58.2%]** (spans zero) and DSR 30%. TECH_EMERGING (-11.1% alpha) and PHARMA_EMERGING (-1.8%) both NO. Survivorship bias inflates all three.

  **🌱 badge validation** (`analysis/badge_validation.py`) — does a badged stock beat the non-badged names in its universe over the next 3–6 months? Forward returns in excess of SPY, non-overlapping windows. **Decisive null:** every spread's 95% CI spans zero.

  | Universe | 3mo spread (CI) | 6mo spread (CI) |
  |---|---|---|
  | TECH_EMERGING   | **−8.6%** [−25.4, +5.1] | −0.9% [−26.4, +20.2] |
  | SEMIS_EMERGING  | **−4.2%** [−13.9, +4.6] | **−4.8%** [−23.4, +12.3] |
  | PHARMA_EMERGING | +5.5% [−3.3, +16.0] | +12.5% [−6.6, +32.4] |

  4 of 6 cells are *negative*; the 2 positive (pharma) include zero. And this is the **look-ahead-flattered** version (current fundamentals applied to past dates — only price signals are point-in-time), so the true edge is likely worse, not better. **Conclusion: the 🌱 badge is a discovery/watchlist tag, not a return predictor — it must not drive buy decisions.** Matches `potential.py`'s own "does NOT predict success" docstring; now empirically confirmed. The clean test still needs point-in-time fundamentals (or snapshot badge labels forward and wait).
