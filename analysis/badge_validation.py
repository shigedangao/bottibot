# analysis/badge_validation.py — Does the 🌱 emerging badge predict anything?
#
# Question: do stocks carrying the EMERGING_POTENTIAL badge outperform the
# non-badged names in the same universe over the next 3–6 months?
#
# ── HONEST DATA CAVEAT (read this) ────────────────────────────────────────
# A clean point-in-time test needs *historical* fundamentals snapshots. yfinance
# only exposes the *current* snapshot (forward P/E, revenue growth, PEG, R&D).
# So at every past date T we label the badge with:
#   • point-in-time price signals (momentum_60d) — correctly as-of T, AND
#   • CURRENT fundamentals — a look-ahead approximation (constant across time).
# The badge's only time-varying input here is therefore momentum. Treat the
# numbers as suggestive, not as a clean backtest. The clean answer requires
# snapshotting badge labels going forward (see --emit-forward) and waiting.
#
# To reduce the worst stats sin, forward windows are NON-OVERLAPPING (test dates
# are spaced `horizon` months apart), and we compare returns in EXCESS of SPY
# over the same window so market beta isn't doing the talking.

from __future__ import annotations

import argparse
import sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UNIVERSES
from data.fetcher import fetch_ohlcv, fetch_fundamentals, fetch_rd_intensity
from analysis.technical import compute_indicators, get_technical_signals
from analysis.potential import detect_emerging_potential

console = Console()

MIN_HISTORY_DAYS = 200  # need ~200 days for EMA200 / momentum signals


def _monthly_first_trading_days(index: pd.DatetimeIndex, lookback_months: int) -> list[pd.Timestamp]:
    """First trading day of each month within the lookback window."""
    end = index[-1]
    start = end - pd.DateOffset(months=lookback_months)
    dates = []
    for m in pd.date_range(start=start, end=end, freq="MS"):
        mask = index >= m
        if mask.any():
            dates.append(index[mask][0])
    return sorted(set(dates))


def _fwd_return(df: pd.DataFrame, entry_date: pd.Timestamp, horizon_months: int) -> float | None:
    """Forward simple return from entry_date to entry_date + horizon_months."""
    exit_date = entry_date + pd.DateOffset(months=horizon_months)
    if exit_date > df.index[-1]:
        return None
    e_idx = df.index.get_indexer([entry_date], method="nearest")[0]
    x_idx = df.index.get_indexer([exit_date], method="nearest")[0]
    e, x = df["close"].iloc[e_idx], df["close"].iloc[x_idx]
    if e <= 0:
        return None
    return float(x / e - 1)


def _two_sample_diff_ci(a: np.ndarray, b: np.ndarray, n_boot=2000, ci=0.95, seed=42):
    """Bootstrap CI for mean(a) - mean(b), resampling each cohort independently."""
    rng = np.random.default_rng(seed)
    if len(a) == 0 or len(b) == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(a.mean() - b.mean())
    boots = np.empty(n_boot)
    for i in range(n_boot):
        ra = a[rng.integers(0, len(a), len(a))]
        rb = b[rng.integers(0, len(b), len(b))]
        boots[i] = ra.mean() - rb.mean()
    lo, hi = np.percentile(boots, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return point, float(lo), float(hi)


def validate_universe(
    universe: str,
    lookback_months: int = 60,
    horizons=(3, 6),
    concurrency: int = 8,
    verbose: bool = True,
) -> dict:
    """
    Collect (badge, forward-excess-return) observations across the lookback and
    compare badged vs non-badged cohorts. Returns per-horizon stats.
    """
    tickers = UNIVERSES[universe]
    period = "10y" if lookback_months >= 48 else "5y"

    bench = fetch_ohlcv("SPY", period=period)
    if bench is None or len(bench) < 252:
        return {}
    bench.index = bench.index.tz_localize(None) if bench.index.tz else bench.index

    # Current fundamentals + R&D (the look-ahead approximation) and price history.
    fundamentals: dict[str, dict] = {}
    rd: dict[str, float | None] = {}
    price: dict[str, pd.DataFrame] = {}

    def _load(t: str):
        df = fetch_ohlcv(t, period=period)
        if df is None or len(df) < 252:
            return t, None, None, None
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        return t, df, fetch_fundamentals(t), fetch_rd_intensity(t)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_load, t) for t in tickers]
        done = 0
        for f in as_completed(futures):
            t, df, fund, rdi = f.result()
            done += 1
            if verbose:
                print(f"\r  [{done}/{len(tickers)}] {t:<10}", end="", flush=True)
            if df is not None:
                price[t], fundamentals[t], rd[t] = df, fund, rdi
    if verbose:
        print(f"\r  ✓ {len(price)}/{len(tickers)} loaded with sufficient history       ")

    if not price:
        return {}

    out: dict[int, dict] = {}
    for h in horizons:
        # Non-overlapping windows: take monthly first-trading-days, step by h.
        all_dates = _monthly_first_trading_days(bench.index, lookback_months)
        test_dates = all_dates[::h]

        badged_x, nonbadged_x = [], []  # forward excess returns vs SPY
        for T in test_dates:
            bench_fwd = _fwd_return(bench, T, h)
            if bench_fwd is None:
                continue
            bench_slice = bench.iloc[: bench.index.get_indexer([T], method="nearest")[0] + 1]
            for t, df in price.items():
                e_idx = df.index.get_indexer([T], method="nearest")[0]
                if e_idx < MIN_HISTORY_DAYS:
                    continue
                fwd = _fwd_return(df, T, h)
                if fwd is None:
                    continue
                try:
                    sig = get_technical_signals(compute_indicators(df.iloc[: e_idx + 1].copy()),
                                                benchmark_df=bench_slice)
                except Exception:
                    continue
                if not sig:
                    continue
                badge = detect_emerging_potential(fundamentals[t], sig, rd[t])
                excess = fwd - bench_fwd
                (badged_x if badge["is_emerging"] else nonbadged_x).append(excess)

        a = np.array(badged_x)
        b = np.array(nonbadged_x)
        diff, lo, hi = _two_sample_diff_ci(a, b)
        out[h] = {
            "n_badged":        len(a),
            "n_nonbadged":     len(b),
            "badged_mean":     float(a.mean()) if len(a) else float("nan"),
            "nonbadged_mean":  float(b.mean()) if len(b) else float("nan"),
            "badged_hit":      float((a > 0).mean()) if len(a) else float("nan"),
            "nonbadged_hit":   float((b > 0).mean()) if len(b) else float("nan"),
            "diff":            diff,
            "diff_ci":         (lo, hi),
        }
    return out


def _print_universe(universe: str, stats: dict):
    table = Table(title=f"🌱 Badge validation — {universe} (forward excess return vs SPY)",
                  border_style="cyan")
    table.add_column("Horizon", style="bold")
    table.add_column("Badged mean", justify="right")
    table.add_column("Non-badged", justify="right")
    table.add_column("Spread", justify="right")
    table.add_column("Spread 95% CI", justify="right")
    table.add_column("Badged hit%", justify="right")
    table.add_column("N (badge/non)", justify="right")

    for h, s in stats.items():
        lo, hi = s["diff_ci"]
        spans_zero = lo <= 0 <= hi
        diff_color = "yellow" if spans_zero else ("green" if s["diff"] > 0 else "red")
        table.add_row(
            f"{h}mo",
            f"{s['badged_mean']*100:+.1f}%",
            f"{s['nonbadged_mean']*100:+.1f}%",
            f"[{diff_color}]{s['diff']*100:+.1f}%[/{diff_color}]",
            f"[{diff_color}][{lo*100:+.1f}, {hi*100:+.1f}][/{diff_color}]",
            f"{s['badged_hit']*100:.0f}%",
            f"{s['n_badged']}/{s['n_nonbadged']}",
        )
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the 🌱 emerging-potential badge")
    parser.add_argument("--universes", nargs="+",
                        default=["TECH_EMERGING", "SEMIS_EMERGING", "PHARMA_EMERGING"],
                        help="Universes to test (default: the three *_EMERGING lists)")
    parser.add_argument("--months", type=int, default=60, help="Lookback window (default 60)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[3, 6],
                        help="Forward horizons in months (default 3 6)")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    console.print(Panel(
        "[bold cyan]🌱 Emerging-badge validation[/bold cyan]\n"
        f"Universes: {', '.join(args.universes)}\n"
        f"Lookback {args.months}mo | horizons {args.horizons} | non-overlapping windows | "
        f"returns in excess of SPY\n"
        "[yellow]Caveat:[/yellow] fundamentals are current-snapshot (look-ahead); only price "
        "signals are point-in-time. Suggestive, not a clean backtest.",
        expand=False,
    ))

    pooled: dict[int, dict] = {h: {"badged": [], "nonbadged": []} for h in args.horizons}
    for u in args.universes:
        console.print(f"\n[bold]── {u} ──[/bold]")
        stats = validate_universe(u, lookback_months=args.months,
                                  horizons=tuple(args.horizons), concurrency=args.concurrency)
        if stats:
            _print_universe(u, stats)

    console.print(
        "\n[dim]How to read it: a positive spread whose 95% CI excludes zero means the badge "
        "separated winners from the rest at that horizon. A CI spanning zero (yellow) means no "
        "detectable edge. Overlapping survivorship and current-fundamentals look-ahead both flatter "
        "the badge, so treat a null result as decisive and a positive result as merely a lead.[/dim]"
    )
