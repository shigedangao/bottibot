# analysis/technical.py — Calcul des indicateurs techniques

import pandas as pd
import numpy as np
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TECHNICAL


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule tous les indicateurs techniques sur un DataFrame OHLCV.
    Retourne le DataFrame enrichi.
    """
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # ── EMAs ──────────────────────────────────────────────────
    df["ema20"]  = close.ewm(span=TECHNICAL["ema_fast"],  adjust=False).mean()
    df["ema50"]  = close.ewm(span=TECHNICAL["ema_slow"],  adjust=False).mean()
    df["ema200"] = close.ewm(span=TECHNICAL["ema_trend"], adjust=False).mean()

    # ── RSI ───────────────────────────────────────────────────
    df["rsi"] = _compute_rsi(close, TECHNICAL["rsi_period"])

    # ── Bollinger Bands ───────────────────────────────────────
    bb_mid = close.rolling(TECHNICAL["bb_period"]).mean()
    bb_std = close.rolling(TECHNICAL["bb_period"]).std()
    df["bb_upper"] = bb_mid + TECHNICAL["bb_std"] * bb_std
    df["bb_lower"] = bb_mid - TECHNICAL["bb_std"] * bb_std
    df["bb_mid"]   = bb_mid
    df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / bb_mid  # volatilité normalisée
    df["bb_pct"]    = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])  # position dans les bandes

    # ── ATR (volatilité) ──────────────────────────────────────
    df["atr"] = _compute_atr(high, low, close, TECHNICAL["atr_period"])
    df["atr_pct"] = df["atr"] / close * 100  # ATR en %

    # ── Volume ────────────────────────────────────────────────
    df["volume_avg"] = volume.rolling(TECHNICAL["volume_avg_period"]).mean()
    df["volume_ratio"] = volume / df["volume_avg"]  # 1.0 = volume normal

    # ── MACD ─────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # ── Momentum (taux de variation sur N jours) ──────────────
    n = TECHNICAL["momentum_period"]
    df["momentum_10d"]  = close.pct_change(10) * 100
    df["momentum_20d"]  = close.pct_change(20) * 100
    df["momentum_60d"]  = close.pct_change(60) * 100
    df["momentum_120d"] = close.pct_change(120) * 100

    # ── ADX (force de la tendance) ────────────────────────────
    df["adx"] = _compute_adx(high, low, close, 14)

    return df


def get_technical_signals(df: pd.DataFrame, benchmark_df: pd.DataFrame | None = None) -> dict:
    """
    Extrait les signaux techniques clés à partir du dernier point du DataFrame.
    Retourne un dict de signaux normalisés entre 0 et 1 (1 = très bullish).
    If benchmark_df is provided, computes relative strength (excess returns vs benchmark).
    """
    if df.empty or len(df) < 50:
        return {}

    row = df.iloc[-1]
    close = row["close"]

    signals = {}

    # ── Signal de tendance EMA ────────────────────────────────
    # Prix au-dessus des 3 EMAs = tendance haussière forte
    above_ema20  = 1 if close > row["ema20"]  else 0
    above_ema50  = 1 if close > row["ema50"]  else 0
    above_ema200 = 1 if close > row["ema200"] else 0
    signals["trend_score"] = (above_ema20 * 0.4 + above_ema50 * 0.35 + above_ema200 * 0.25)

    # EMA alignment (ema20 > ema50 > ema200 = parfait)
    ema_aligned = (row["ema20"] > row["ema50"]) and (row["ema50"] > row["ema200"])
    signals["ema_aligned"] = 1.0 if ema_aligned else 0.0

    # ── Signal RSI ────────────────────────────────────────────
    rsi = row["rsi"]
    if pd.isna(rsi):
        signals["rsi_score"] = 0.5
    elif rsi < TECHNICAL["rsi_oversold"]:
        # Survendu = opportunité d'achat potentielle
        signals["rsi_score"] = 0.8
    elif rsi > TECHNICAL["rsi_overbought"]:
        # Suracheté = prudence
        signals["rsi_score"] = 0.2
    else:
        # Zone neutre : idéalement autour de 50-60 (tendance haussière saine)
        signals["rsi_score"] = min(1.0, (rsi - 30) / 40)

    signals["rsi_value"] = rsi

    # ── Signal Volume ─────────────────────────────────────────
    vol_ratio = row["volume_ratio"] if not pd.isna(row["volume_ratio"]) else 1.0
    # Volume 2x la moyenne = confirmation forte
    signals["volume_score"] = min(1.0, vol_ratio / 2.0)
    signals["volume_ratio"] = vol_ratio

    # ── Signal Momentum ───────────────────────────────────────
    m10  = row["momentum_10d"]  if not pd.isna(row["momentum_10d"])  else 0
    m20  = row["momentum_20d"]  if not pd.isna(row["momentum_20d"])  else 0
    m60  = row["momentum_60d"]  if not pd.isna(row["momentum_60d"])  else 0
    m120 = row["momentum_120d"] if not pd.isna(row["momentum_120d"]) else 0

    # Score momentum pondéré (court terme compte plus)
    mom_raw = m10 * 0.4 + m20 * 0.3 + m60 * 0.2 + m120 * 0.1
    # Normaliser : -30% → 0, +30% → 1
    signals["momentum_score"] = max(0.0, min(1.0, (mom_raw + 30) / 60))
    signals["momentum_10d"]  = m10
    signals["momentum_20d"]  = m20
    signals["momentum_60d"]  = m60

    # ── Relative Strength vs Benchmark ────────────────────────
    if benchmark_df is not None and len(benchmark_df) >= 60:
        bench_close = benchmark_df["close"]
        b10  = (bench_close.iloc[-1] / bench_close.iloc[-10] - 1) * 100 if len(bench_close) >= 10 else 0
        b20  = (bench_close.iloc[-1] / bench_close.iloc[-20] - 1) * 100 if len(bench_close) >= 20 else 0
        b60  = (bench_close.iloc[-1] / bench_close.iloc[-60] - 1) * 100 if len(bench_close) >= 60 else 0

        # Excess return = stock return - benchmark return
        excess_10  = m10 - b10
        excess_20  = m20 - b20
        excess_60  = m60 - b60
        excess_raw = excess_10 * 0.4 + excess_20 * 0.3 + excess_60 * 0.3

        # Normalize: -20% excess → 0, +20% excess → 1
        signals["relative_strength_score"] = max(0.0, min(1.0, (excess_raw + 20) / 40))
        signals["excess_return_60d"] = round(excess_60, 1)
    else:
        signals["relative_strength_score"] = 0.5
        signals["excess_return_60d"] = 0.0

    # ── MACD ─────────────────────────────────────────────────
    signals["macd_bullish"] = 1.0 if row["macd"] > row["macd_signal"] else 0.0
    signals["macd_hist"]    = row["macd_hist"]

    # ── ADX ───────────────────────────────────────────────────
    signals["adx"] = row["adx"] if not pd.isna(row["adx"]) else 20
    signals["trend_strong"] = 1.0 if row["adx"] > 25 else 0.5

    # ── Position dans les Bollinger Bands ─────────────────────
    signals["bb_pct"] = row["bb_pct"] if not pd.isna(row["bb_pct"]) else 0.5

    # ── Volatilité (ATR%) ─────────────────────────────────────
    signals["atr_pct"] = row["atr_pct"] if not pd.isna(row["atr_pct"]) else 2.0

    # ── Prix vs 52w ───────────────────────────────────────────
    signals["pct_from_high_52w"] = (close / df["close"].max() - 1) * 100
    signals["pct_from_low_52w"]  = (close / df["close"].min() - 1) * 100

    return signals


# ─────────────────────────────────────────────────────────────
# Helpers privés
# ─────────────────────────────────────────────────────────────

def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ADX simplifié."""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    plus_dm  = high.diff()
    minus_dm = -low.diff()

    plus_dm  = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    atr      = tr.ewm(span=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
    adx = dx.ewm(span=period, adjust=False).mean()

    return adx
