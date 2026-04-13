# scoring/engine.py — Moteur de scoring composite

import pandas as pd
import numpy as np
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SCORING_WEIGHTS, TECHNICAL, VIX


def _get_adjusted_weights(vix_regime: str | None) -> dict:
    """Return scoring weights adjusted for the current VIX regime."""
    base = dict(SCORING_WEIGHTS)
    if vix_regime == "ELEVATED":
        adj = VIX["elevated_adj"]
    elif vix_regime == "PANIC":
        adj = VIX["panic_adj"]
    else:
        return base
    return {k: base[k] + adj.get(k, 0) for k in base}


def compute_final_score(
    tech_signals: dict,
    fund_signals: dict,
    fundamentals: dict,
    vix_regime: str | None = None,
) -> dict:
    """
    Calcule le score final composite (0-100) à partir des signaux
    techniques et fondamentaux.
    Retourne un dict avec le score, le détail, et une recommandation.
    """
    w = _get_adjusted_weights(vix_regime)

    # ── Composantes du score ──────────────────────────────────
    # Blend absolute momentum (60%) with relative strength vs benchmark (40%)
    abs_momentum = tech_signals.get("momentum_score", 0.5)
    rel_strength = tech_signals.get("relative_strength_score", 0.5)
    momentum_score  = abs_momentum * 0.6 + rel_strength * 0.4
    trend_score     = tech_signals.get("trend_score", 0.5)
    rsi_score       = tech_signals.get("rsi_score", 0.5)
    volume_score    = tech_signals.get("volume_score", 0.5)
    fund_score      = fund_signals.get("fundamental_score", 0.5)
    quality_score   = fund_signals.get("quality_score", 0.5)

    # Bonus si EMA alignées + MACD bullish (tendance forte confirmée)
    trend_bonus = 0.0
    if tech_signals.get("ema_aligned") and tech_signals.get("macd_bullish"):
        trend_bonus = 0.05

    # Score brut pondéré
    raw_score = (
        momentum_score  * w["momentum"]   +
        trend_score     * w["trend"]      +
        rsi_score       * w["rsi"]        +
        volume_score    * w["volume"]     +
        fund_score      * w["fundamental"] +
        quality_score   * w["quality"]    +
        trend_bonus
    )

    # Normaliser sur 100
    final_score = min(100, raw_score * 100)

    # ── Recommandation ────────────────────────────────────────
    recommendation, color, emoji = _get_recommendation(
        final_score, tech_signals, fund_signals
    )

    # ── Raisons principales (pour l'affichage) ─────────────────
    reasons = _build_reasons(tech_signals, fund_signals, fundamentals)

    # ── Stop-loss / Take-profit suggérés ──────────────────────
    atr_pct = tech_signals.get("atr_pct", 2.0)
    risk_reward = _compute_risk_reward(atr_pct, final_score)

    return {
        "score":              round(final_score, 1),
        "recommendation":     recommendation,
        "color":              color,
        "emoji":              emoji,
        "reasons":            reasons,
        # Détail des composantes
        "momentum_component":   round(momentum_score  * w["momentum"]   * 100, 1),
        "trend_component":      round(trend_score     * w["trend"]      * 100, 1),
        "rsi_component":        round(rsi_score       * w["rsi"]        * 100, 1),
        "volume_component":     round(volume_score    * w["volume"]     * 100, 1),
        "fundamental_component":round(fund_score      * w["fundamental"]* 100, 1),
        "quality_component":    round(quality_score   * w["quality"]    * 100, 1),
        # Risk management
        "suggested_stop_loss":  risk_reward["stop_loss_pct"],
        "suggested_take_profit":risk_reward["take_profit_pct"],
        "risk_reward_ratio":    risk_reward["rr_ratio"],
    }


def _get_recommendation(score: float, tech: dict, fund: dict) -> tuple[str, str, str]:
    """Détermine la recommandation textuelle."""

    # Cas particuliers
    if tech.get("rsi_value", 50) > TECHNICAL["rsi_overbought"]:
        if score > 65:
            return "SURVEILLER", "orange", "👀"

    if score >= 75:
        return "FORT ACHAT",   "green",  "🟢"
    elif score >= 62:
        return "ACHAT",        "lightgreen", "📈"
    elif score >= 50:
        return "NEUTRE",       "gray",   "⚪"
    elif score >= 38:
        return "PRUDENCE",     "orange", "🟡"
    else:
        return "ÉVITER",       "red",    "🔴"


def _build_reasons(tech: dict, fund: dict, fundamentals: dict) -> list[str]:
    """Construit une liste de raisons humainement lisibles."""
    reasons = []

    # Trend
    if tech.get("ema_aligned"):
        reasons.append("✅ Bullish trend: EMA20 > EMA50 > EMA200")
    elif tech.get("trend_score", 0) > 0.6:
        reasons.append("📈 Partial bullish trend")
    else:
        reasons.append("⚠️ Bearish or mixed trend")

    # Momentum + relative strength
    m60 = tech.get("momentum_60d", 0)
    excess = tech.get("excess_return_60d", 0)
    if m60 > 20:
        reasons.append(f"🚀 Strong momentum: +{m60:.1f}% over 60d")
    elif m60 > 5:
        reasons.append(f"📊 Positive momentum: +{m60:.1f}% over 60d")
    elif m60 < -10:
        reasons.append(f"📉 Negative momentum: {m60:.1f}% over 60d")

    if excess > 10:
        reasons.append(f"💪 Outperforming SPY by +{excess:.1f}% over 60d")
    elif excess < -10:
        reasons.append(f"📉 Underperforming SPY by {excess:.1f}% over 60d")

    # RSI
    rsi = tech.get("rsi_value", 50)
    if rsi < TECHNICAL["rsi_oversold"]:
        reasons.append(f"💡 RSI oversold ({rsi:.0f}) — potential bounce")
    elif rsi > TECHNICAL["rsi_overbought"]:
        reasons.append(f"⚠️ RSI overbought ({rsi:.0f}) — caution")
    else:
        reasons.append(f"✅ Healthy RSI ({rsi:.0f})")

    # Volume
    vol_ratio = tech.get("volume_ratio", 1.0)
    if vol_ratio > 1.5:
        reasons.append(f"📊 High volume ({vol_ratio:.1f}x average)")

    # Fundamentals
    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None and rev_growth > 0.20:
        reasons.append(f"💹 Strong revenue growth: +{rev_growth*100:.0f}%")

    gross_m = fundamentals.get("gross_margin")
    if gross_m is not None and gross_m > 0.50:
        reasons.append(f"💰 High gross margin: {gross_m*100:.0f}%")

    # Quality
    if fund.get("quality_score", 0) > 0.70:
        reasons.append("⭐ High quality company")

    # Exclusions
    for reason in fund.get("reasons_exclude", []):
        reasons.append(f"❌ {reason}")

    return reasons[:7]


def _compute_risk_reward(atr_pct: float, score: float) -> dict:
    """
    Calcule des niveaux stop-loss / take-profit suggérés
    basés sur l'ATR et le niveau de conviction.
    """
    # Stop-loss = 1.5x ATR (sous le cours actuel)
    stop_loss_pct = round(-atr_pct * 1.5, 1)

    # Take-profit = selon le score (plus le score est élevé, plus l'objectif est ambitieux)
    if score >= 75:
        tp_mult = 3.0
    elif score >= 62:
        tp_mult = 2.0
    else:
        tp_mult = 1.5

    take_profit_pct = round(atr_pct * 1.5 * tp_mult, 1)

    rr = abs(take_profit_pct / stop_loss_pct) if stop_loss_pct != 0 else 1.5

    return {
        "stop_loss_pct":    stop_loss_pct,
        "take_profit_pct":  take_profit_pct,
        "rr_ratio":         round(rr, 1),
    }


def rank_stocks(results: list[dict], max_per_sector: int = 0) -> list[dict]:
    """
    Sort results by score descending.
    If max_per_sector > 0, cap the number of stocks per sector to ensure diversification.
    """
    valid = [r for r in results if r.get("score") is not None]
    ranked = sorted(valid, key=lambda x: x["score"], reverse=True)

    if max_per_sector <= 0:
        return ranked

    diversified = []
    sector_counts: dict[str, int] = {}
    for r in ranked:
        sector = r.get("sector", "Unknown")
        count = sector_counts.get(sector, 0)
        if count < max_per_sector:
            diversified.append(r)
            sector_counts[sector] = count + 1
        # Skip stocks that exceed the sector cap (they stay in full ranked list)

    return diversified
