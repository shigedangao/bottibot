# analysis/ic.py — Information Coefficient measurement
#
# Pure functions for measuring how well a signal rank-predicts forward returns.
# IC = Spearman rank correlation between (signal, forward return) at one point
# in time. Aggregating IC across many periods gives mean IC, IC stability (std),
# the Information Ratio (mean / std × √periods), and a t-stat for "IC ≠ 0".
#
# These are the standard quant metrics used to decide whether a signal has
# predictive content before worrying about portfolio construction or costs.

from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def spearman_ic(scores: dict[str, float], forward_returns: dict[str, float]) -> float | None:
    """
    Rank correlation between a signal and forward returns at one point in time.

    Returns None if fewer than 5 paired observations are available — too few
    to be informative. Pairs are formed by intersecting tickers present in
    both inputs and dropping NaNs.
    """
    if not scores or not forward_returns:
        return None

    common = set(scores) & set(forward_returns)
    if len(common) < 5:
        return None

    s = pd.Series({t: scores[t] for t in common}, dtype="float64")
    r = pd.Series({t: forward_returns[t] for t in common}, dtype="float64")

    paired = pd.concat([s, r], axis=1).dropna()
    if len(paired) < 5:
        return None

    # Spearman = Pearson on ranks. Implemented manually so we don't pull in
    # scipy just for this — pandas' method="spearman" requires it.
    ranks = paired.rank()
    ic = ranks.iloc[:, 0].corr(ranks.iloc[:, 1])
    if pd.isna(ic):
        return None
    return float(ic)


def quintile_spread(
    scores: dict[str, float],
    forward_returns: dict[str, float],
    q: int = 5,
) -> dict | None:
    """
    Bucket stocks into q equal-sized buckets by score and report the mean
    forward return of the top bucket, the bottom bucket, and the spread.

    Quintile spread is the long-only top-N strategy's bread and butter —
    Spearman IC measures full-cross-section rank correlation, but a top-N
    portfolio only cares whether the right tail of the score distribution
    has higher returns than the left tail. A signal can have low IC yet
    decent quintile spread (or vice versa).

    Returns None if there are fewer than 2*q paired observations — too few
    to form meaningful buckets.
    """
    if not scores or not forward_returns:
        return None

    common = set(scores) & set(forward_returns)
    if len(common) < 2 * q:
        return None

    s = pd.Series({t: scores[t] for t in common}, dtype="float64")
    r = pd.Series({t: forward_returns[t] for t in common}, dtype="float64")
    paired = pd.concat([s, r], axis=1).dropna()
    paired.columns = ["score", "ret"]
    if len(paired) < 2 * q:
        return None

    # Bucket by score rank — qcut on rank() handles ties cleanly without the
    # "Bin edges must be unique" failure raw qcut hits when many scores tie.
    try:
        paired["bucket"] = pd.qcut(paired["score"].rank(method="first"), q=q, labels=False)
    except ValueError:
        return None

    top = paired.loc[paired["bucket"] == q - 1, "ret"]
    bot = paired.loc[paired["bucket"] == 0, "ret"]
    if top.empty or bot.empty:
        return None

    top_ret = float(top.mean())
    bot_ret = float(bot.mean())
    return {
        "top":     top_ret,
        "bottom":  bot_ret,
        "spread":  top_ret - bot_ret,
        "n_top":   int(len(top)),
        "n_bottom": int(len(bot)),
    }


def spread_summary(period_spreads: Iterable[float | None], periods_per_year: int = 12) -> dict:
    """Aggregate per-period quintile spreads (mean spread, t-stat, hit rate)."""
    spreads = [x for x in period_spreads if x is not None and not math.isnan(x)]
    n = len(spreads)
    if n == 0:
        return {
            "n_periods": 0,
            "mean_spread": None,
            "std_spread": None,
            "t_stat_spread": None,
            "hit_rate_spread": None,
            "annualized_spread": None,
        }

    s = pd.Series(spreads, dtype="float64")
    mean_spread = float(s.mean())
    std_spread = float(s.std(ddof=1)) if n > 1 else 0.0
    hit = float((s > 0).mean())

    if std_spread > 0 and n > 1:
        t_stat = mean_spread / (std_spread / math.sqrt(n))
    else:
        t_stat = None

    # Annualized via simple compounding of mean spread (approximation —
    # ignores higher-order moments but fine as a single-number summary).
    annualized = (1 + mean_spread) ** periods_per_year - 1 if mean_spread > -1 else None

    return {
        "n_periods": n,
        "mean_spread": mean_spread,
        "std_spread": std_spread,
        "t_stat_spread": t_stat,
        "hit_rate_spread": hit,
        "annualized_spread": annualized,
    }


def ic_summary(period_ics: Iterable[float], periods_per_year: int = 12) -> dict:
    """
    Aggregate per-period ICs into the headline statistics.

    - mean_ic       — average rank correlation
    - std_ic        — period-to-period stability
    - ir            — Information Ratio = mean / std × √periods_per_year
                      (annualized risk-adjusted predictive strength)
    - hit_rate      — fraction of periods with positive IC
    - t_stat        — t-statistic for H0: mean IC = 0 (≥3 is the bar Harvey/Liu/Zhu
                      argue for in the factor-zoo paper)
    - n_periods     — number of periods contributing to the average
    """
    ics = [x for x in period_ics if x is not None and not math.isnan(x)]
    n = len(ics)
    if n == 0:
        return {
            "n_periods": 0,
            "mean_ic": None,
            "std_ic": None,
            "ir": None,
            "hit_rate": None,
            "t_stat": None,
        }

    s = pd.Series(ics, dtype="float64")
    mean_ic = float(s.mean())
    std_ic = float(s.std(ddof=1)) if n > 1 else 0.0
    hit_rate = float((s > 0).mean())

    if std_ic > 0 and n > 1:
        ir = mean_ic / std_ic * math.sqrt(periods_per_year)
        t_stat = mean_ic / (std_ic / math.sqrt(n))
    else:
        ir = None
        t_stat = None

    return {
        "n_periods": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "ir": ir,
        "hit_rate": hit_rate,
        "t_stat": t_stat,
    }
