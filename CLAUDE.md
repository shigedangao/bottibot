# bottibot — Context pour Claude Code

## Projet
Stock Analyzer + futur Crypto Trading Bot. Développé avec Marc (développeur backend Go/Rust/Python chez Kaiko, novice en finance).

## Ce qui est déjà construit (Session 1)

Architecture complète du **Stock Analyzer** :

```
bottibot/
├── config.py              # Univers d'actions, poids de scoring, seuils fondamentaux
├── main.py                # Screener CLI avec Rich (tableau + détail top 3)
├── data/fetcher.py        # Yahoo Finance — OHLCV + fondamentaux
├── analysis/
│   ├── technical.py       # EMA20/50/200, RSI, MACD, Bollinger, ATR, ADX, Momentum
│   └── fundamental.py     # Marges, ROE, P/E, PEG, croissance CA/EPS, santé bilan
├── scoring/engine.py      # Score 0-100 pondéré + stop-loss/take-profit suggérés (ATR-based)
└── dashboard/app.py       # Streamlit : classement, scatter, graphique bougies, détail
```

## Méthode de scoring

| Composante  | Poids | Logique |
|-------------|-------|---------|
| Momentum    | 25%   | Perf 10j/20j/60j/120j pondérée, normalisée -30%→0 / +30%→1 |
| Tendance    | 25%   | EMA20>EMA50>EMA200, bonus si alignées + MACD bullish |
| Fondamental | 20%   | Qualité×0.35 + Croissance×0.30 + Valeur×0.20 + Santé×0.15 |
| Qualité     | 10%   | Marge brute, marge opé, ROE |
| RSI         | 10%   | <35 survendu=0.8, >70 suracheté=0.2, sinon linéaire |
| Volume      | 10%   | volume/volume_avg_20j, capé à 1.0 pour ratio≥2 |

Score → Recommandation : 75+ FORT ACHAT · 62+ ACHAT · 50+ NEUTRE · 38+ PRUDENCE · <38 ÉVITER

Stop-loss = -1.5×ATR% · Take-profit = SL × (3.0 si score≥75, 2.0 si ≥62, 1.5 sinon)

## Stack
- Python 3.12, yfinance, pandas, numpy, Streamlit, Plotly, Rich

## Roadmap
1. Tester + calibrer le screener, ajuster les poids dans config.py
2. Alertes Telegram/email quand score > seuil
3. Crypto Trading Bot (Binance API, paper trading → réel avec 500€)
   - Stratégie : Mean Reversion en ranging, Momentum en trending
   - Spot uniquement, pas de levier

## Conventions
- Tout paramétrable dans config.py (pas de magic numbers dans le code)
- Scores 0.0-1.0 dans les modules, ×100 uniquement dans scoring/engine.py
- Erreurs silencieuses par ticker (un échec ne plante pas le screener)

## Commandes utiles
```bash
python main.py --tickers AAPL NVDA MSFT ASML.AS MC.PA
python main.py --universe EU_LARGE --top 20
streamlit run dashboard/app.py
```
