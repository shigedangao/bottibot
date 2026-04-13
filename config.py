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
# ──────────────────────────────────────────────
SCORING_WEIGHTS = {
    "momentum":     0.25,   # tendance des prix court terme
    "trend":        0.25,   # structure de tendance (EMA)
    "rsi":          0.10,   # RSI : ni suracheté, ni survendu
    "volume":       0.10,   # confirmation du volume
    "fundamental":  0.20,   # santé financière
    "quality":      0.10,   # profitabilité (marge, ROE)
}

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
