# config.py — Configuration centrale du Stock Analyzer

# ──────────────────────────────────────────────
# Univers d'actions à screener
# On commence avec un échantillon représentatif
# ──────────────────────────────────────────────
UNIVERSES = {
    "US_LARGE": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO",
        "JPM", "V", "MA", "UNH", "XOM", "LLY", "JNJ", "WMT", "PG",
        "HD", "MRK", "ABBV", "CVX", "KO", "PEP", "COST", "ADBE",
        "CRM", "TMO", "ACN", "MCD", "NKE", "NFLX", "AMD", "INTC",
        "QCOM", "TXN", "AMAT", "LRCX", "ASML", "NOW", "SNOW",
    ],
    "EU_LARGE": [
        "AIR.PA", "MC.PA", "OR.PA", "SAN.PA", "BNP.PA", "TTE.PA",
        "SU.PA", "DG.PA", "RI.PA", "SAF.PA", "CAP.PA", "SGO.PA",
        "ABI.BR", "ASML.AS", "PHIA.AS", "ING.AS", "AD.AS",
        "SIE.DE", "ALV.DE", "BMW.DE", "MBG.DE", "BAS.DE", "BAYN.DE",
        "DTE.DE", "VOW3.DE", "DBK.DE", "ADS.DE",
        "NOVN.SW", "ROG.SW", "NESN.SW",
        "GSK.L", "AZN.L", "HSBA.L", "BP.L", "RIO.L", "SHEL.L",
    ],
    "GROWTH_TECH": [
        # Cybersecurity & infra
        "PLTR", "CRWD", "DDOG", "NET", "ZS", "PANW", "FTNT", "S",
        # SaaS & cloud
        "MNDY", "TEAM", "HUBS", "MDB", "CFLT", "SNOW", "NOW",
        # Fintech & e-commerce
        "MELI", "SE", "GRAB", "SHOP", "XYZ", "PYPL", "AFRM",
        # Mobility & travel
        "UBER", "LYFT", "DASH", "ABNB", "BKNG",
        # Entertainment & AI
        "SPOT", "RBLX", "U", "TTWO", "EA",
        "AI", "PATH", "ASAN",
    ],
    "SMALL_MID": [
        "SMCI", "ARM", "AXON", "MSTR", "COIN", "HOOD",
        "IONQ", "RGTI", "QUBT", "BBAI",
        "CELH", "HIMS", "RDNT", "ACMR",
    ],
    "ASIA_LARGE": [
        # Japan
        "7203.T", "6758.T", "6902.T", "8306.T", "9984.T",  # Toyota, Sony, Denso, MUFG, SoftBank
        "6861.T", "6367.T", "7741.T", "4063.T", "6594.T",  # Keyence, Daikin, HOYA, Shin-Etsu, Nidec
        "8035.T", "6723.T",                                  # Tokyo Electron, Renesas
        # South Korea
        "005930.KS", "000660.KS", "373220.KS",              # Samsung, SK Hynix, LG Energy
        # Taiwan
        "2330.TW", "2454.TW", "2317.TW",                    # TSMC, MediaTek, Hon Hai
        # Hong Kong / China
        "9988.HK", "0700.HK", "9618.HK", "9888.HK",        # Alibaba, Tencent, JD, Baidu
        "1211.HK", "3690.HK",                                # BYD, Meituan
        # India
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", # Reliance, TCS, Infosys, HDFC
        # Australia
        "BHP.AX", "CSL.AX", "CBA.AX",                       # BHP, CSL, Commonwealth Bank
    ],
    "SEMICONDUCTORS": [
        "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN",      # US majors
        "AMAT", "LRCX", "KLAC", "SNPS", "CDNS",             # Equipment & EDA
        "MRVL", "ON", "NXPI", "MCHP", "ADI", "MU",          # Analog / memory / mixed
        "ARM", "SMCI",                                        # ARM, Super Micro
        "ASML.AS",                                             # EU (ASML)
        "2330.TW", "2454.TW",                                 # TSMC, MediaTek
        "005930.KS", "000660.KS",                             # Samsung, SK Hynix
        "8035.T", "6723.T",                                    # Tokyo Electron, Renesas
    ],
    "PHARMA_BIOTECH": [
        # US large pharma
        "LLY", "JNJ", "MRK", "ABBV", "PFE", "BMY", "AMGN", "GILD",
        # US biotech
        "VRTX", "REGN", "MRNA", "BIIB", "ALNY", "BMRN", "SGEN",
        # Med devices & tools
        "TMO", "ISRG", "SYK", "MDT", "ABT", "DHR", "EW",
        # EU pharma
        "AZN.L", "GSK.L", "NOVN.SW", "ROG.SW", "SAN.PA", "BAYN.DE",
        # Asia pharma
        "4568.T", "4519.T", "CSL.AX",                        # Daiichi Sankyo, Chugai, CSL
    ],
    # ──────────────────────────────────────────────
    # Emerging counterparts — smaller / earlier-stage names per domain.
    # Lower market cap, less analyst coverage, higher risk-and-upside than the
    # mega-cap lists above. Same scoring; the 🌱 EMERGING_POTENTIAL badge is
    # more likely to fire here. Curated by hand — edit freely.
    # ──────────────────────────────────────────────
    "TECH_EMERGING": [
        # Software / data / AI infra (mid & small cap)
        "GTLB", "FROG", "ESTC", "DOCN", "BRZE", "AMPL", "PD",
        "PCOR", "BL", "APPN", "FSLY", "BOX", "DV", "SOUN", "BBAI",
        # Cybersecurity challengers
        "TENB", "RPD", "CXM", "VRNS",
    ],
    "SEMIS_EMERGING": [
        # Smaller chip designers, analog, equipment & EDA (not the mega-caps)
        "ALGM", "POWI", "SITM", "CRUS", "SLAB", "LSCC", "AMBA", "RMBS",
        "SMTC", "ONTO", "ACLS", "FORM", "UCTT", "CEVA", "INDI", "NVTS",
    ],
    "PHARMA_EMERGING": [
        # Mid & small biotech, gene editing, med-tech challengers
        "CRSP", "NTLA", "BEAM", "RXRX", "VKTX", "ARWR", "SRPT", "RARE",
        "HALO", "EXEL", "INSM", "CYTK", "MDGL", "IONS", "ACAD", "ARVN",
    ],
}

# Tous les tickers combinés pour le screener global
ALL_TICKERS = list({t for tickers in UNIVERSES.values() for t in tickers})

# ──────────────────────────────────────────────
# Paramètres techniques
# ──────────────────────────────────────────────
TECHNICAL = {
    "ema_fast": 20,
    "ema_slow": 50,
    "ema_trend": 200,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 70,
    "bb_period": 20,
    "bb_std": 2,
    "atr_period": 14,
    "volume_avg_period": 20,
    "momentum_period": 10,
    "lookback_days": 365,       # données historiques à charger
    # Definition used by momentum_score in get_technical_signals.
    # IC + quintile-spread validation on 60m, 4 universes (RESEARCH_PLAN.md status log):
    #   "residual_12_1" — 12-1 of residuals from monthly stock-on-benchmark regression
    #             (Blitz/Huij/Martens 2011). Default. Avg annualized quintile spread
    #             +16.6% across 4 universes (vs +12.0% for raw 12_1). Major
    #             improvement on GROWTH_TECH (+1.7% → +17.8%) and EU_LARGE
    #             (+8.5% → +15.8%); slight cost on US_LARGE and SEMIS.
    #   "12_1"  — Raw 12-month return, skip last month. Jegadeesh-Titman / Carhart.
    #             4/4 universes positive but weaker on sector-concentrated baskets
    #             where market-beta noise dominates.
    #   "12"    — 12-month return, no skip. Highest IR on US_LARGE alone but noisier.
    #   "6_1"   — 6-1 variant. ~Equivalent to legacy.
    #   "60d"   — Raw 60-day return.
    #   "legacy" — Original 10/20/60/120 weighted blend. Anti-predictive in 3/4
    #             universes during validation. Kept reachable for A/B comparison.
    "momentum_definition": "residual_12_1",
}

# ──────────────────────────────────────────────
# Paramètres fondamentaux (seuils de filtrage)
# ──────────────────────────────────────────────
FUNDAMENTAL = {
    "min_market_cap": 500e6,       # 500M$ minimum
    "max_debt_to_ebitda": 5.0,     # dette/EBITDA max acceptable
    "min_gross_margin": 0.20,      # marge brute min 20%
    "min_revenue_growth": -0.10,   # croissance CA > -10% (on garde les stables)
    "max_pe_ratio": 80,            # P/E max (pour éviter les bulles extrêmes)
    "min_pe_ratio": 0,             # on exclut les pertes nettes
}

# ──────────────────────────────────────────────
# Liquidity filter (tradeability)
# Average daily dollar volume = mean(close × volume) over `lookback_days`.
# Below `min_avg_dollar_volume`, the slippage assumptions in the cost model no
# longer hold and a retail order moves the price — so these names are dropped
# from the screener (and therefore the digest). Especially relevant for the
# *_EMERGING universes. Set min to 0 (or pass --min-dollar-volume 0) to disable.
# ──────────────────────────────────────────────
LIQUIDITY = {
    "min_avg_dollar_volume": 5_000_000.0,   # $5M/day floor for ~30 bps slippage to be realistic
    "lookback_days": 20,
}

# ──────────────────────────────────────────────
# Sector benchmarks for relative scoring
# Each sector has typical gross_margin, operating_margin, roe, pe, revenue_growth
# Values are "good" reference points — stock scores relative to these
# ──────────────────────────────────────────────
SECTOR_BENCHMARKS = {
    "Technology": {
        "gross_margin": 0.65, "operating_margin": 0.25, "roe": 0.25,
        "pe": 30, "revenue_growth": 0.15, "debt_to_equity": 60,
    },
    "Healthcare": {
        "gross_margin": 0.65, "operating_margin": 0.20, "roe": 0.20,
        "pe": 25, "revenue_growth": 0.10, "debt_to_equity": 80,
    },
    "Financial Services": {
        "gross_margin": 0.55, "operating_margin": 0.30, "roe": 0.12,
        "pe": 15, "revenue_growth": 0.08, "debt_to_equity": 150,
    },
    "Consumer Cyclical": {
        "gross_margin": 0.40, "operating_margin": 0.12, "roe": 0.18,
        "pe": 22, "revenue_growth": 0.08, "debt_to_equity": 80,
    },
    "Consumer Defensive": {
        "gross_margin": 0.40, "operating_margin": 0.15, "roe": 0.20,
        "pe": 22, "revenue_growth": 0.05, "debt_to_equity": 80,
    },
    "Communication Services": {
        "gross_margin": 0.55, "operating_margin": 0.20, "roe": 0.15,
        "pe": 20, "revenue_growth": 0.08, "debt_to_equity": 80,
    },
    "Industrials": {
        "gross_margin": 0.35, "operating_margin": 0.12, "roe": 0.15,
        "pe": 20, "revenue_growth": 0.06, "debt_to_equity": 100,
    },
    "Energy": {
        "gross_margin": 0.40, "operating_margin": 0.15, "roe": 0.15,
        "pe": 12, "revenue_growth": 0.05, "debt_to_equity": 60,
    },
    "Basic Materials": {
        "gross_margin": 0.35, "operating_margin": 0.15, "roe": 0.12,
        "pe": 15, "revenue_growth": 0.05, "debt_to_equity": 60,
    },
    "Real Estate": {
        "gross_margin": 0.55, "operating_margin": 0.30, "roe": 0.08,
        "pe": 35, "revenue_growth": 0.05, "debt_to_equity": 120,
    },
    "Utilities": {
        "gross_margin": 0.40, "operating_margin": 0.20, "roe": 0.10,
        "pe": 18, "revenue_growth": 0.04, "debt_to_equity": 120,
    },
}
# Fallback for unknown sectors
SECTOR_BENCHMARK_DEFAULT = {
    "gross_margin": 0.45, "operating_margin": 0.15, "roe": 0.15,
    "pe": 20, "revenue_growth": 0.08, "debt_to_equity": 80,
}

# ──────────────────────────────────────────────
# Poids du score final (doivent sommer à 1.0)
#
# Two presets:
# - FIXED: original hand-picked balance, kept for A/B reversibility.
# - IC:    derived from 60m IC sweep across 4 universes (US_LARGE, EU_LARGE,
#          GROWTH_TECH, SEMICONDUCTORS). Each technical signal's avg IR was
#          floored at 0 and renormalized within the 0.70 technical budget.
#
# Average IR by signal (60m sweep, RESEARCH_PLAN.md status log):
#   residual momentum: +0.52  → ~67% of technical budget → 0.47 absolute
#   trend:             -0.04  → floored to 0
#   rsi:               +0.14  → ~18% → 0.13
#   volume:            +0.12  → ~15% → 0.10
# Fundamental/quality (0.20/0.10) unchanged — not yet IC-validated since
# backtest excludes fundamentals to avoid look-ahead.
# ──────────────────────────────────────────────
SCORING_WEIGHTS_FIXED = {
    "momentum":     0.25,
    "trend":        0.25,
    "rsi":          0.10,
    "volume":       0.10,
    "fundamental":  0.20,
    "quality":      0.10,
}
SCORING_WEIGHTS_IC = {
    "momentum":     0.47,
    "trend":        0.00,
    "rsi":          0.13,
    "volume":       0.10,
    "fundamental":  0.20,
    "quality":      0.10,
}
# Active preset — flip to SCORING_WEIGHTS_FIXED to revert hand-picked balance.
SCORING_WEIGHTS = SCORING_WEIGHTS_IC

# ──────────────────────────────────────────────
# VIX / Market regime
# ──────────────────────────────────────────────
VIX = {
    "ticker": "^VIX",
    # Regime thresholds
    "calm_max": 20,         # VIX < 20 = calm market
    "elevated_max": 30,     # 20-30 = elevated volatility
                            # > 30 = panic
    # Weight adjustments per regime (added to base weights, must sum to 0)
    "elevated_adj": {       # shift away from momentum toward quality
        "momentum":    -0.07,
        "trend":       -0.03,
        "rsi":          0.00,
        "volume":       0.00,
        "fundamental":  0.05,
        "quality":      0.05,
    },
    "panic_adj": {          # strong shift to fundamentals/quality
        "momentum":    -0.12,
        "trend":       -0.05,
        "rsi":          0.02,
        "volume":       0.00,
        "fundamental":  0.08,
        "quality":      0.07,
    },
}

# ──────────────────────────────────────────────
# Emerging potential badge
# Forward-looking signals — separate tag, NOT folded into the 0-100 score.
# Awarded when at least `min_signals_required` of the 4 signals fire.
# ──────────────────────────────────────────────
EMERGING_POTENTIAL = {
    "min_signals_required": 2,
    # Forward earnings step-up: forward_pe < trailing_pe * ratio (or trailing missing/negative)
    "forward_pe_step_up_ratio": 0.7,
    "max_forward_pe": 80,                  # ignore bubble forward P/Es
    # Growth not yet priced in: revenue_growth high, but 60d momentum still weak
    "min_revenue_growth_priced_out": 0.20,
    "max_momentum_60d_priced_out": 5.0,    # %
    # Attractive PEG with growth
    "max_peg": 1.5,
    "min_revenue_growth_for_peg": 0.15,
    # Heavy R&D investment (ASML / pre-EUV pattern). R&D / revenue ratio.
    "rd_intensity_default": 0.08,
    "rd_intensity_by_sector": {
        "Technology":             0.13,
        "Healthcare":             0.12,
        "Communication Services": 0.10,
    },
}

# ──────────────────────────────────────────────
# Backtest — transaction cost model
# Per-side cost in basis points (1 bp = 0.01%). Default 15 bps reflects:
#   ~5 bps commission/fees (Degiro/IBKR for liquid US large-caps)
#   ~10 bps slippage (bid/ask + minor market impact)
# Bump to 25-40 bps for small-caps, illiquid markets, or aggressive turnover.
# Round-trip cost on a fully-rotated position = 2 × cost_per_side_bps.
# ──────────────────────────────────────────────
BACKTEST = {
    "cost_per_side_bps": 15.0,
    # Per-side cost presets by universe type. large_cap = liquid US/EU mega-caps
    # (Degiro/IBKR fees + tight spreads). small_cap doubles it to reflect wider
    # spreads and real market impact on smaller / emerging names — use this when
    # backtesting the *_EMERGING universes via --cost-preset small_cap.
    "cost_presets": {
        "large_cap": 15.0,
        "small_cap": 30.0,
    },
    "default_lookback_months": 36,
    # Stickiness — currently-held positions get this many points added during
    # the rebalance sort, so a challenger must beat a held name by more than
    # this gap to displace it. Reduces turnover and cost drag.
    # 0.0 = pure top-N every month; 5.0 = mild stickiness; 10.0 = strong.
    "stickiness_bonus_pts": 5.0,
    # Regime filter — go to cash when SPY trades below its long MA.
    # Classic trend-following rule. Default OFF: empirically (60-month sweep)
    # the filter eats more alpha from SPY 200d-MA whipsaws (2022-23) than it
    # saves in drawdown — it underperformed across all four universes when ON,
    # and made MDD worse on US_LARGE (-23% → -33%) and GROWTH_TECH (-46% → -60%).
    # Kept as an option (--regime-filter not exposed yet, but flip the default)
    # since longer windows or different universes might tell a different story.
    "regime_filter_enabled": False,
    "regime_ma_window":      200,
    # Universes used in --sweep when no explicit list is provided
    "sweep_universes": ["US_LARGE", "EU_LARGE", "GROWTH_TECH", "SEMICONDUCTORS"],
    # Deploy verdict — multi-criteria readout, NOT financial advice.
    # All four conditions must hold to earn the label. Negative alpha → "NO".
    # max_drawdown is negative; thresholds are floors (e.g. -0.40 = MDD must be ≥ -40%).
    "deploy_thresholds": {
        "strong": {"alpha_net": 0.05, "sharpe": 0.70, "win_rate": 0.45, "max_drawdown_floor": -0.40},
        "ok":     {"alpha_net": 0.02, "sharpe": 0.50, "win_rate": 0.40, "max_drawdown_floor": -0.50},
    },
    # Statistical hygiene (Phase 0.3)
    "n_boot":           1000,   # bootstrap iterations for CIs
    "bootstrap_ci":     0.95,   # 95% confidence intervals
    # n_trials_for_dsr: number of variants tested while developing the strategy.
    # Drives the Deflated Sharpe Ratio's multi-test correction. Bumped each
    # time we A/B a meaningful new variant in the research workflow. Be
    # honest about this — undercounting inflates DSR, overcounting deflates
    # it. Counts variants explicitly tested via IC sweeps + backtests, not
    # every read-only diagnostic.
    "n_trials_for_dsr": 20,
}

# ──────────────────────────────────────────────
# Timeframes d'analyse
# ──────────────────────────────────────────────
TIMEFRAMES = {
    "short":  "1d",   # signaux daily
    "period": "1y",   # 1 an d'historique
}

# ──────────────────────────────────────────────
# Paramètres dashboard
# ──────────────────────────────────────────────
DASHBOARD = {
    "top_n": 15,             # nombre d'actions à afficher
    "refresh_hours": 4,      # rafraîchissement auto (heures)
}
