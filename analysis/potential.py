# analysis/potential.py — Emerging potential badge
#
# Forward-looking "future leader" tag — separate from the 0-100 score.
# This is intentionally a noisy signal (for every ASML there are 100 misses):
# the badge flags candidates worth a closer look, it does NOT predict success.
#
# Empirically confirmed (2026-06-12): `analysis/badge_validation.py` found NO
# detectable forward edge — across TECH/SEMIS/PHARMA_EMERGING, the 3–6mo excess
# return of badged vs non-badged names had 95% CIs spanning zero (4 of 6 cells
# negative), and that's the look-ahead-flattered version. Treat this as a
# discovery/watchlist tag only; do NOT let it drive buy decisions.
# See RESEARCH_PLAN.md status log.

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EMERGING_POTENTIAL


SIGNAL_LABELS = {
    "forward_earnings_step_up":   "🔮 Forward earnings step-up expected",
    "growth_not_yet_priced_in":   "💤 Strong growth, market hasn't priced it in",
    "peg_attractive_with_growth": "💰 PEG attractive for the growth rate",
    "heavy_rd_investment":        "🧪 Heavy R&D investment (pre-payoff phase)",
}


def detect_emerging_potential(
    fundamentals: dict,
    tech_signals: dict,
    rd_intensity: float | None = None,
) -> dict:
    """
    Returns {"is_emerging": bool, "signals": list[str], "rd_intensity": float|None}.
    The badge is awarded when EMERGING_POTENTIAL["min_signals_required"] signals fire.
    """
    cfg = EMERGING_POTENTIAL
    fired: list[str] = []

    # 1) Forward earnings step-up — analysts pricing in a meaningful jump
    fwd_pe = fundamentals.get("forward_pe")
    pe = fundamentals.get("pe_ratio")
    if fwd_pe is not None and 0 < fwd_pe < cfg["max_forward_pe"]:
        if pe is None or pe <= 0 or fwd_pe < pe * cfg["forward_pe_step_up_ratio"]:
            fired.append("forward_earnings_step_up")

    # 2) Growth not yet priced in — strong revenue growth with flat/weak 60d price
    rev_growth = fundamentals.get("revenue_growth")
    mom_60d = tech_signals.get("momentum_60d", 0.0)
    if (
        rev_growth is not None
        and rev_growth >= cfg["min_revenue_growth_priced_out"]
        and mom_60d <= cfg["max_momentum_60d_priced_out"]
    ):
        fired.append("growth_not_yet_priced_in")

    # 3) Attractive PEG combined with real growth
    peg = fundamentals.get("peg_ratio")
    if (
        peg is not None and 0 < peg < cfg["max_peg"]
        and rev_growth is not None
        and rev_growth >= cfg["min_revenue_growth_for_peg"]
    ):
        fired.append("peg_attractive_with_growth")

    # 4) Heavy R&D investment vs sector norm
    sector = fundamentals.get("sector")
    rd_threshold = cfg["rd_intensity_by_sector"].get(sector, cfg["rd_intensity_default"])
    if rd_intensity is not None and rd_intensity >= rd_threshold:
        fired.append("heavy_rd_investment")

    return {
        "is_emerging":  len(fired) >= cfg["min_signals_required"],
        "signals":      fired,
        "rd_intensity": rd_intensity,
    }


def format_potential_reasons(signals: list[str]) -> list[str]:
    """Map signal keys to human-readable strings for display."""
    return [SIGNAL_LABELS[s] for s in signals if s in SIGNAL_LABELS]
