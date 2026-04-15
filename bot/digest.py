# bot/digest.py — Morning digest logic.
#
# Pure logic: runs the screener on chosen universes, diffs against the previous
# snapshot, and returns a structured digest. Delivery (Telegram, stdout, email)
# is handled elsewhere.

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UNIVERSES
from main import run_screener
from bot.storage import save_snapshot, load_previous_snapshot

BUY_SIGNALS = {"FORT ACHAT", "ACHAT"}
SCORE_MOVE_THRESHOLD = 5.0  # absolute score points


def _by_ticker(results: list[dict]) -> dict[str, dict]:
    return {r["ticker"]: r for r in results}


def _score_movers(current: list[dict], previous: list[dict]) -> list[dict]:
    """Tickers whose score changed by more than SCORE_MOVE_THRESHOLD since previous snapshot."""
    prev_map = _by_ticker(previous)
    movers = []
    for r in current:
        prev = prev_map.get(r["ticker"])
        if not prev:
            continue
        delta = r["score"] - prev["score"]
        if abs(delta) >= SCORE_MOVE_THRESHOLD:
            movers.append({**r, "score_delta": round(delta, 1), "previous_score": prev["score"]})
    movers.sort(key=lambda x: abs(x["score_delta"]), reverse=True)
    return movers


def _signal_transitions(current: list[dict], previous: list[dict]) -> dict[str, list[dict]]:
    """New buy-signal entries and drop-outs since previous snapshot."""
    prev_map = _by_ticker(previous)
    entered, dropped = [], []
    for r in current:
        prev = prev_map.get(r["ticker"])
        was_buy = prev and prev["recommendation"] in BUY_SIGNALS
        is_buy = r["recommendation"] in BUY_SIGNALS
        if is_buy and not was_buy:
            entered.append(r)
        elif was_buy and not is_buy:
            dropped.append({**r, "previous_recommendation": prev["recommendation"]})
    return {"entered_buy": entered, "dropped_buy": dropped}


def generate_digest(
    universe: str = "US_LARGE",
    top_n: int = 5,
    concurrency: int = 5,
) -> dict:
    """Run the screener and build a structured digest against the previous snapshot."""
    tickers = UNIVERSES[universe]
    previous = load_previous_snapshot()

    current = run_screener(tickers=tickers, top_n=top_n, concurrency=concurrency)

    digest = {
        "universe": universe,
        "top_n": top_n,
        "top": current[:top_n],
        "earnings_soon": [r for r in current if r.get("earnings_soon")],
        "has_previous": previous is not None,
        "score_movers": [],
        "entered_buy": [],
        "dropped_buy": [],
    }

    if previous:
        digest["score_movers"] = _score_movers(current, previous)[:5]
        transitions = _signal_transitions(current, previous)
        digest["entered_buy"] = transitions["entered_buy"]
        digest["dropped_buy"] = transitions["dropped_buy"]

    save_snapshot(current)
    return digest


if __name__ == "__main__":
    import argparse
    from bot.formatting import format_digest_markdown

    parser = argparse.ArgumentParser(description="Generate morning digest")
    parser.add_argument("--universe", default="US_LARGE", choices=list(UNIVERSES.keys()))
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    digest = generate_digest(universe=args.universe, top_n=args.top, concurrency=args.concurrency)
    print("\n" + "=" * 60)
    print(format_digest_markdown(digest))
