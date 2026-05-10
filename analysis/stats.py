# analysis/stats.py — Bootstrap CIs + Deflated Sharpe Ratio
#
# Statistical hygiene for backtests. Two purposes:
#   1) Bootstrap confidence intervals so we report ranges, not point estimates.
#   2) Deflated Sharpe Ratio (Bailey & López de Prado 2014) — adjusts the
#      observed Sharpe for (a) non-Normal returns and (b) the inflation that
#      comes from trying many variants.
#
# Note on scope: a simple resample-with-replacement bootstrap assumes IID
# returns. Monthly portfolio returns have mild autocorrelation; a block
# bootstrap would be more correct. Keeping it simple here — the headline
# question is "how wide is the 95% band?", not a precise distribution.

from __future__ import annotations

from math import erf, log, sqrt
from typing import Callable

import numpy as np


def _phi(z: float) -> float:
    """Standard normal CDF via math.erf — avoids a scipy dependency."""
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def bootstrap_ci(
    returns: np.ndarray,
    fn: Callable[[np.ndarray], float],
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int | None = 42,
) -> tuple[float, float, float]:
    """
    Bootstrap a confidence interval for a one-sample statistic.
    Returns (point_estimate, lower_bound, upper_bound).
    """
    rng = np.random.default_rng(seed)
    n = len(returns)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(fn(returns))
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = fn(returns[idx])
    lo, hi = np.percentile(boots, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return point, float(lo), float(hi)


def bootstrap_pairs_ci(
    a: np.ndarray,
    b: np.ndarray,
    fn: Callable[[np.ndarray, np.ndarray], float],
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int | None = 42,
) -> tuple[float, float, float]:
    """Paired bootstrap for two-sample stats like alpha = port - bench."""
    rng = np.random.default_rng(seed)
    n = len(a)
    if n == 0 or len(b) != n:
        return float("nan"), float("nan"), float("nan")
    point = float(fn(a, b))
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = fn(a[idx], b[idx])
    lo, hi = np.percentile(boots, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return point, float(lo), float(hi)


def deflated_sharpe_ratio(
    returns: np.ndarray,
    n_trials: int = 1,
    periods_per_year: int = 12,
) -> dict:
    """
    Bailey & López de Prado (2014) — Deflated Sharpe Ratio.

    Two corrections to the naive Sharpe:
      - Higher-moment correction: PSR (Probabilistic Sharpe Ratio) accounts
        for the fact that with non-Normal returns (skew, fat tails) the
        sampling distribution of the Sharpe is wider than Normal theory
        suggests, so the observed Sharpe is less informative than it looks.
      - Multi-trial correction: when you try N strategies, the expected max
        Sharpe under the null is > 0. DSR uses that max-under-null as the
        threshold instead of 0, asking "does our Sharpe beat the threshold
        we'd expect from data-mining N strategies?"

    Returns:
      sharpe_annualized : the observed Sharpe (annualized)
      psr_zero          : P(true Sharpe > 0) given the sample
      sr_threshold_ann  : expected max Sharpe under null with n_trials (annualized)
      dsr               : P(true Sharpe > sr_threshold) — the real survival measure
      skew              : sample skewness of returns
      excess_kurtosis   : sample (excess) kurtosis
      n_periods         : number of period returns
      n_trials          : multi-test correction parameter passed in

    Interpretation:
      - PSR > 0.95: 95% confident the strategy has positive true Sharpe (single test).
      - DSR > 0.95: 95% confident the Sharpe beats what we'd expect from
                    data-mining N strategies. This is the bar to clear.
    """
    n = len(returns)
    if n < 3:
        return {
            "sharpe_annualized": None,
            "psr_zero":          None,
            "sr_threshold_ann":  None,
            "dsr":               None,
            "skew":              None,
            "excess_kurtosis":   None,
            "n_periods":         n,
            "n_trials":          n_trials,
        }

    mean_r = float(np.mean(returns))
    std_r = float(np.std(returns, ddof=1))
    if std_r <= 0:
        return {
            "sharpe_annualized": 0.0,
            "psr_zero":          None,
            "sr_threshold_ann":  None,
            "dsr":               None,
            "skew":              0.0,
            "excess_kurtosis":   0.0,
            "n_periods":         n,
            "n_trials":          n_trials,
        }

    z = (returns - mean_r) / std_r
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))         # raw kurtosis (3 = Normal)
    excess_kurt = kurt - 3.0

    # Period Sharpe (not annualized — annualization applied at output)
    sr = mean_r / std_r
    sr_ann = sr * sqrt(periods_per_year)

    def _psr(sr_threshold_period: float) -> float | None:
        # PSR formula: Phi((SR - SR*) * sqrt(n-1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2))
        denom_sq = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
        if denom_sq <= 0:
            return None
        zscore = (sr - sr_threshold_period) * sqrt(n - 1) / sqrt(denom_sq)
        return _phi(zscore)

    psr_zero = _psr(0.0)

    # Expected max Sharpe under H0 across n_trials (asymptotic extreme-value
    # approximation for max of N standard normals):
    #   E[max] ≈ V * (1 - γ) * Φ⁻¹(1 - 1/N) + V * γ * Φ⁻¹(1 - 1/(N*e))
    # where V is the std of trials' Sharpes and γ ≈ 0.5772 (Euler-Mascheroni).
    # Without prior estimate of V we use a conservative simplification:
    #   threshold ≈ sqrt(2 * log(N)) / sqrt(T-1)  (period units)
    # which is the asymptotic max of N iid N(0, 1/sqrt(T-1)) variables.
    if n_trials >= 2:
        sr_threshold_period = sqrt(2.0 * log(n_trials)) / sqrt(n - 1)
        sr_threshold_ann = sr_threshold_period * sqrt(periods_per_year)
        dsr = _psr(sr_threshold_period)
    else:
        sr_threshold_ann = 0.0
        dsr = psr_zero

    return {
        "sharpe_annualized": sr_ann,
        "psr_zero":          psr_zero,
        "sr_threshold_ann":  sr_threshold_ann,
        "dsr":               dsr,
        "skew":              skew,
        "excess_kurtosis":   excess_kurt,
        "n_periods":         n,
        "n_trials":          n_trials,
    }


# ─────────────────────────────────────────────────────────────
# Convenience statistics for use as `fn` arguments.
# ─────────────────────────────────────────────────────────────

def cagr(monthly_returns: np.ndarray, periods_per_year: int = 12) -> float:
    if len(monthly_returns) == 0:
        return 0.0
    cum = float(np.prod(1.0 + monthly_returns))
    years = len(monthly_returns) / periods_per_year
    if years <= 0 or cum <= 0:
        return 0.0
    return cum ** (1.0 / years) - 1.0


def sharpe(monthly_returns: np.ndarray, periods_per_year: int = 12) -> float:
    if len(monthly_returns) < 2:
        return 0.0
    s = float(np.std(monthly_returns, ddof=1))
    if s <= 0:
        return 0.0
    return float(np.mean(monthly_returns)) / s * sqrt(periods_per_year)


def cagr_diff(port: np.ndarray, bench: np.ndarray, periods_per_year: int = 12) -> float:
    """Alpha as the geometric-mean difference (CAGR(port) - CAGR(bench))."""
    return cagr(port, periods_per_year) - cagr(bench, periods_per_year)
