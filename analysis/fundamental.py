# analysis/fundamental.py — Analyse des données fondamentales (sector-relative)

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FUNDAMENTAL, SECTOR_BENCHMARKS, SECTOR_BENCHMARK_DEFAULT


def _get_sector_benchmark(sector: str | None) -> dict:
    """Return the benchmark for a given sector, or the default."""
    if sector and sector in SECTOR_BENCHMARKS:
        return SECTOR_BENCHMARKS[sector]
    return SECTOR_BENCHMARK_DEFAULT


def _score_vs_benchmark(value, benchmark, higher_is_better=True, scale=2.0):
    """
    Score a metric relative to its sector benchmark.
    Returns 0.0-1.0 where 0.5 = at benchmark, 1.0 = scale× better, 0.0 = scale× worse.
    """
    if value is None or benchmark is None or benchmark == 0:
        return 0.5
    ratio = value / benchmark
    if not higher_is_better:
        ratio = 1 / ratio if ratio != 0 else 1.0
    # Map ratio to 0-1: ratio=1.0 → 0.5, ratio=scale → 1.0, ratio=1/scale → 0.0
    normalized = 0.5 + 0.5 * (ratio - 1.0) / (scale - 1.0)
    return max(0.0, min(1.0, normalized))


def get_fundamental_signals(fundamentals: dict) -> dict:
    """
    Calcule des scores fondamentaux normalisés entre 0 et 1,
    relative to sector benchmarks.
    """
    signals = {
        "is_valid": False,
        "fundamental_score": 0.0,
        "quality_score": 0.0,
        "growth_score": 0.0,
        "value_score": 0.0,
        "health_score": 0.0,
        "reasons_exclude": [],
    }

    sector = fundamentals.get("sector")
    bench = _get_sector_benchmark(sector)

    # ── Exclusion checks ─────────────────────────────────────
    market_cap = fundamentals.get("market_cap")
    if market_cap and market_cap < FUNDAMENTAL["min_market_cap"]:
        signals["reasons_exclude"].append(f"Market cap too low ({_fmt_cap(market_cap)})")
        return signals

    pe = fundamentals.get("pe_ratio")
    if pe and pe > FUNDAMENTAL["max_pe_ratio"]:
        signals["reasons_exclude"].append(f"P/E too high ({pe:.0f}x)")

    gross_margin = fundamentals.get("gross_margin")
    # Use sector-relative minimum: 50% of sector benchmark
    sector_min_margin = bench["gross_margin"] * 0.5
    if gross_margin is not None and gross_margin < sector_min_margin:
        signals["reasons_exclude"].append(
            f"Gross margin low for {sector or 'sector'} ({gross_margin*100:.1f}% vs {bench['gross_margin']*100:.0f}% benchmark)"
        )

    signals["is_valid"] = True

    # ── Quality score (profitability vs sector) ───────────────
    quality_scores = []

    if gross_margin is not None:
        quality_scores.append(_score_vs_benchmark(gross_margin, bench["gross_margin"]))

    op_m = fundamentals.get("operating_margin")
    if op_m is not None:
        quality_scores.append(_score_vs_benchmark(op_m, bench["operating_margin"]))

    roe = fundamentals.get("return_on_equity")
    if roe is not None:
        quality_scores.append(_score_vs_benchmark(roe, bench["roe"]))

    signals["quality_score"] = sum(quality_scores) / max(len(quality_scores), 1)

    # ── Growth score (vs sector expectations) ─────────────────
    growth_scores = []

    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None:
        growth_scores.append(_score_vs_benchmark(rev_growth, bench["revenue_growth"], scale=3.0))

    earn_growth = fundamentals.get("earnings_growth")
    if earn_growth is not None:
        growth_scores.append(_score_vs_benchmark(earn_growth, bench["revenue_growth"], scale=3.0))

    signals["growth_score"] = sum(growth_scores) / max(len(growth_scores), 1)

    # ── Value score (P/E vs sector) ───────────────────────────
    value_scores = []

    if pe is not None and pe > 0:
        # Lower P/E is better relative to sector
        value_scores.append(_score_vs_benchmark(pe, bench["pe"], higher_is_better=False))

    peg = fundamentals.get("peg_ratio")
    if peg is not None and peg > 0:
        # PEG < 1 = undervalued, > 3 = overvalued
        value_scores.append(max(0.0, min(1.0, 1.0 - (peg - 0.5) / 2.5)))

    signals["value_score"] = sum(value_scores) / max(len(value_scores), 1) if value_scores else 0.5

    # ── Health score (balance sheet vs sector) ────────────────
    health_scores = []

    dte = fundamentals.get("debt_to_equity")
    if dte is not None:
        health_scores.append(_score_vs_benchmark(dte, bench["debt_to_equity"], higher_is_better=False))

    cr = fundamentals.get("current_ratio")
    if cr is not None:
        # CR 2+ = good, < 1 = bad (universal, not sector-relative)
        health_scores.append(max(0.0, min(1.0, (cr - 0.5) / 1.5)))

    fcf = fundamentals.get("free_cashflow")
    if fcf is not None:
        health_scores.append(1.0 if fcf > 0 else 0.2)

    signals["health_score"] = sum(health_scores) / max(len(health_scores), 1) if health_scores else 0.5

    # ── Composite fundamental score ───────────────────────────
    signals["fundamental_score"] = (
        signals["quality_score"]  * 0.35 +
        signals["growth_score"]   * 0.30 +
        signals["value_score"]    * 0.20 +
        signals["health_score"]   * 0.15
    )

    return signals


def format_fundamentals_display(fundamentals: dict, fund_signals: dict) -> dict:
    """Format fundamental data for dashboard display."""
    def pct(v):
        return f"{v*100:.1f}%" if v is not None else "N/A"

    def num(v, decimals=1):
        return f"{v:.{decimals}f}" if v is not None else "N/A"

    def cap(v):
        return _fmt_cap(v) if v is not None else "N/A"

    return {
        "Name":             fundamentals.get("name", "N/A"),
        "Sector":           fundamentals.get("sector", "N/A"),
        "Market Cap":       cap(fundamentals.get("market_cap")),
        "P/E":              num(fundamentals.get("pe_ratio")),
        "PEG":              num(fundamentals.get("peg_ratio")),
        "P/B":              num(fundamentals.get("price_to_book")),
        "Gross Margin":     pct(fundamentals.get("gross_margin")),
        "EBITDA Margin":    pct(fundamentals.get("ebitda_margin")),
        "Operating Margin": pct(fundamentals.get("operating_margin")),
        "ROE":              pct(fundamentals.get("return_on_equity")),
        "Revenue Growth":   pct(fundamentals.get("revenue_growth")),
        "Earnings Growth":  pct(fundamentals.get("earnings_growth")),
        "D/E":              num(fundamentals.get("debt_to_equity")),
        "Current Ratio":    num(fundamentals.get("current_ratio")),
        "Quality Score":    f"{fund_signals.get('quality_score', 0)*100:.0f}/100",
        "Growth Score":     f"{fund_signals.get('growth_score', 0)*100:.0f}/100",
        "Value Score":      f"{fund_signals.get('value_score', 0)*100:.0f}/100",
        "Health Score":     f"{fund_signals.get('health_score', 0)*100:.0f}/100",
    }


def _fmt_cap(v: float) -> str:
    if v >= 1e12:
        return f"${v/1e12:.1f}T"
    elif v >= 1e9:
        return f"${v/1e9:.1f}B"
    elif v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:.0f}"
