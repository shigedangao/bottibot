# ic.py — Information Coefficient runner
#
# Measures how well a signal rank-predicts forward 1-month returns across
# a universe. For each rebalance date, scores every ticker, looks at the
# next-period return, computes Spearman rank correlation, then aggregates
# across periods (mean IC, IR, hit rate, t-stat).
#
# Kept separate from backtest.py because the questions differ:
#   - Backtest: "would top-N have made money net of costs?"
#   - IC:       "does the signal rank-predict returns at all?"
#
# Use --signal to test individual components (momentum / trend / etc.) so we
# can spot redundancy and identify which sub-signals carry the predictive load.

import argparse
import sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ALL_TICKERS, UNIVERSES, SCORING_WEIGHTS, BACKTEST
from data.fetcher import fetch_ohlcv
from analysis.technical import compute_indicators, get_technical_signals
from analysis.ic import spearman_ic, ic_summary, quintile_spread, spread_summary

console = Console()


def _composite_technical_score(tech_signals: dict) -> float:
    """Composite technical-only score (0-100), mirrors backtest.py."""
    w = SCORING_WEIGHTS
    tech_total = w["momentum"] + w["trend"] + w["rsi"] + w["volume"]

    abs_momentum = tech_signals.get("momentum_score", 0.5)
    rel_strength = tech_signals.get("relative_strength_score", 0.5)
    momentum = abs_momentum * 0.6 + rel_strength * 0.4

    raw = (
        momentum * w["momentum"]
        + tech_signals.get("trend_score", 0.5) * w["trend"]
        + tech_signals.get("rsi_score", 0.5) * w["rsi"]
        + tech_signals.get("volume_score", 0.5) * w["volume"]
    ) / tech_total

    if tech_signals.get("ema_aligned") and tech_signals.get("macd_bullish"):
        raw += 0.05

    return min(100.0, raw * 100)


def _nan_get(key: str):
    """Extractor that returns NaN when a signal is missing.
    Lets the IC harness drop missing-history tickers cleanly instead of
    giving them a tied-rank value of 0 that would corrupt the correlation."""
    def _f(s: dict) -> float:
        v = s.get(key)
        if v is None:
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")
    return _f


def _legacy_momentum_blend(s: dict) -> float:
    """Config-independent reproduction of the original 10/20/60/120 weighted
    blend. Lives here so we can A/B against it regardless of what the
    production momentum_definition is currently set to."""
    m10  = s.get("momentum_10d",  0) or 0
    m20  = s.get("momentum_20d",  0) or 0
    m60  = s.get("momentum_60d",  0) or 0
    m120 = s.get("momentum_120d", 0) or 0
    return m10 * 0.4 + m20 * 0.3 + m60 * 0.2 + m120 * 0.1


SIGNAL_FNS: dict[str, Callable[[dict], float]] = {
    "composite":         _composite_technical_score,
    "momentum":          lambda s: s.get("momentum_score", 0.5) * 100,
    "rel_strength":      lambda s: s.get("relative_strength_score", 0.5) * 100,
    "trend":             lambda s: s.get("trend_score", 0.5) * 100,
    "rsi":               lambda s: s.get("rsi_score", 0.5) * 100,
    "volume":            lambda s: s.get("volume_score", 0.5) * 100,
    "momentum_60d":      _nan_get("momentum_60d"),
    "excess_60d":        _nan_get("excess_return_60d"),
    "momentum_12":       _nan_get("momentum_12"),
    "momentum_12_1":     _nan_get("momentum_12_1"),
    "momentum_6_1":          _nan_get("momentum_6_1"),
    "momentum_legacy":       _legacy_momentum_blend,
    "residual_momentum_12_1": _nan_get("residual_momentum_12_1"),
    "beta_36m":              _nan_get("beta_36m"),
    "bab":                   lambda s: -s["beta_36m"] if s.get("beta_36m") is not None and not pd.isna(s.get("beta_36m")) else float("nan"),
}


def _score_at_date(
    full_df: pd.DataFrame,
    benchmark_slice: pd.DataFrame,
    as_of_idx: int,
    signal_fn: Callable[[dict], float],
) -> Optional[float]:
    """Score a ticker using only data available up to as_of_idx."""
    if as_of_idx < 200:
        return None
    df_slice = full_df.iloc[: as_of_idx + 1].copy()
    try:
        df_ind = compute_indicators(df_slice)
        signals = get_technical_signals(df_ind, benchmark_df=benchmark_slice)
        if not signals:
            return None
        return signal_fn(signals)
    except Exception:
        return None


def _get_rebalance_dates(bench_index: pd.DatetimeIndex, lookback_months: int) -> list[pd.Timestamp]:
    end = bench_index[-1]
    start = end - pd.DateOffset(months=lookback_months)
    months = pd.date_range(start=start, end=end, freq="MS")
    dates = []
    for m in months:
        mask = bench_index >= m
        if mask.any():
            dates.append(bench_index[mask][0])
    return sorted(set(dates))


def run_ic(
    tickers: list[str],
    signal_name: str = "composite",
    lookback_months: int = 24,
    benchmark_ticker: str = "SPY",
    concurrency: int = 5,
    label: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Run an Information Coefficient analysis.
    Returns a dict with per-period IC, summary stats, and metadata.
    """
    if signal_name not in SIGNAL_FNS:
        raise ValueError(f"Unknown signal '{signal_name}'. Available: {list(SIGNAL_FNS)}")
    signal_fn = SIGNAL_FNS[signal_name]

    if verbose:
        title = label or "IC analysis"
        console.print(Panel(
            f"[bold cyan]📐 {title}[/bold cyan]\n"
            f"Signal: [bold]{signal_name}[/bold] | Universe: {len(tickers)} tickers | "
            f"Lookback: {lookback_months} months\n"
            f"Forward horizon: 1 month (next rebalance close)",
            expand=False,
        ))

    period = "10y" if lookback_months >= 48 else "5y" if lookback_months >= 24 else "3y"

    if verbose:
        console.print(f"[dim]Fetching {benchmark_ticker} benchmark...[/dim]")
    bench_df = fetch_ohlcv(benchmark_ticker, period=period)
    if bench_df is None or len(bench_df) < 252:
        if verbose:
            console.print("[red]Failed to fetch benchmark data[/red]")
        return {}
    bench_df.index = bench_df.index.tz_localize(None) if bench_df.index.tz else bench_df.index

    if verbose:
        console.print(f"[dim]Fetching {len(tickers)} tickers (concurrency={concurrency})...[/dim]")
    ticker_dfs: dict[str, pd.DataFrame] = {}

    def _fetch_one(t: str):
        df = fetch_ohlcv(t, period=period)
        if df is not None and len(df) >= 252:
            df.index = df.index.tz_localize(None) if df.index.tz else df.index
            return t, df
        return t, None

    completed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_fetch_one, t) for t in tickers]
        for future in as_completed(futures):
            t, df = future.result()
            completed += 1
            if verbose:
                print(f"\r  [{completed}/{len(tickers)}] {t:<12}", end="", flush=True)
            if df is not None:
                ticker_dfs[t] = df
    if verbose:
        print(f"\r  ✓ {len(ticker_dfs)}/{len(tickers)} tickers loaded with sufficient history           ")

    if not ticker_dfs:
        return {}

    rebalance_dates = _get_rebalance_dates(bench_df.index, lookback_months)
    if len(rebalance_dates) < 2:
        if verbose:
            console.print("[red]Not enough rebalance dates[/red]")
        return {}

    period_records: list[dict] = []

    for period_idx in range(len(rebalance_dates) - 1):
        entry_date = rebalance_dates[period_idx]
        exit_date = rebalance_dates[period_idx + 1]

        bench_entry_idx = bench_df.index.get_indexer([entry_date], method="nearest")[0]
        bench_slice = bench_df.iloc[: bench_entry_idx + 1]

        scores: dict[str, float] = {}
        forward_returns: dict[str, float] = {}

        for ticker, df in ticker_dfs.items():
            entry_idx_arr = df.index.get_indexer([entry_date], method="nearest")
            exit_idx_arr = df.index.get_indexer([exit_date], method="nearest")
            if len(entry_idx_arr) == 0 or len(exit_idx_arr) == 0:
                continue
            entry_idx = entry_idx_arr[0]
            exit_idx = exit_idx_arr[0]

            score = _score_at_date(df, bench_slice, entry_idx, signal_fn)
            if score is None:
                continue

            entry_price = df["close"].iloc[entry_idx]
            exit_price = df["close"].iloc[exit_idx]
            if entry_price <= 0:
                continue

            scores[ticker] = score
            forward_returns[ticker] = exit_price / entry_price - 1

        ic = spearman_ic(scores, forward_returns)
        qs = quintile_spread(scores, forward_returns, q=5)
        period_records.append({
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "exit_date":  exit_date.strftime("%Y-%m-%d"),
            "n_tickers":  len(scores),
            "ic":         ic,
            "spread":     qs["spread"] if qs else None,
            "top_ret":    qs["top"] if qs else None,
            "bot_ret":    qs["bottom"] if qs else None,
        })

    ic_stats = ic_summary([p["ic"] for p in period_records], periods_per_year=12)
    spread_stats = spread_summary([p["spread"] for p in period_records], periods_per_year=12)

    results = {
        "label":           label or "IC analysis",
        "signal":          signal_name,
        "lookback_months": lookback_months,
        "n_periods":       len(period_records),
        "periods":         period_records,
        **ic_stats,
        **spread_stats,
    }

    if verbose:
        _print_results(results)
    return results


def _print_results(r: dict):
    """Print IC summary and recent per-period detail."""
    table = Table(title="Per-period IC + quintile spread (last 12)", border_style="bright_black")
    table.add_column("Entry", style="dim")
    table.add_column("Exit", style="dim")
    table.add_column("N", justify="right")
    table.add_column("IC", justify="right")
    table.add_column("Top", justify="right")
    table.add_column("Bot", justify="right")
    table.add_column("Spread", justify="right")

    for p in r["periods"][-12:]:
        ic = p["ic"]
        ic_str = "[dim]n/a[/dim]" if ic is None else f"[{'green' if ic > 0 else 'red'}]{ic:+.3f}[/]"
        top = p.get("top_ret")
        bot = p.get("bot_ret")
        spread = p.get("spread")
        top_str = "n/a" if top is None else f"{top*100:+.1f}%"
        bot_str = "n/a" if bot is None else f"{bot*100:+.1f}%"
        sp_str = (
            "[dim]n/a[/dim]" if spread is None
            else f"[{'green' if spread > 0 else 'red'}]{spread*100:+.1f}%[/]"
        )
        table.add_row(p["entry_date"], p["exit_date"], str(p["n_tickers"]), ic_str, top_str, bot_str, sp_str)
    console.print(table)
    if len(r["periods"]) > 12:
        console.print(f"[dim](showing last 12 of {len(r['periods'])} periods)[/dim]\n")

    summary = Table(title="IC summary", show_header=False, border_style="cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")

    mean_ic = r["mean_ic"]
    ir = r["ir"]
    t_stat = r["t_stat"]
    hit = r["hit_rate"]

    if mean_ic is None:
        summary.add_row("Mean IC", "[dim]n/a[/dim]")
    else:
        ic_color = "green" if mean_ic > 0 else "red"
        summary.add_row("Mean IC", f"[{ic_color}]{mean_ic:+.4f}[/{ic_color}]")
    summary.add_row("IC std", "n/a" if r["std_ic"] is None else f"{r['std_ic']:.4f}")
    if ir is None:
        summary.add_row("Information Ratio (annualized)", "[dim]n/a[/dim]")
    else:
        ir_color = "green" if ir > 0 else "red"
        summary.add_row("Information Ratio (annualized)", f"[{ir_color}]{ir:+.2f}[/{ir_color}]")
    if hit is None:
        summary.add_row("Hit rate (% periods IC > 0)", "[dim]n/a[/dim]")
    else:
        hit_color = "green" if hit > 0.5 else "yellow"
        summary.add_row("Hit rate (% periods IC > 0)", f"[{hit_color}]{hit*100:.0f}%[/{hit_color}]")
    if t_stat is None:
        summary.add_row("t-stat (H0: mean IC = 0)", "[dim]n/a[/dim]")
    else:
        t_color = "green" if abs(t_stat) >= 3.0 else "yellow" if abs(t_stat) >= 2.0 else "red"
        summary.add_row("t-stat (H0: mean IC = 0)", f"[{t_color}]{t_stat:+.2f}[/{t_color}]")
    summary.add_row("Periods", str(r["n_periods"]))

    # Quintile spread block — what a top-N portfolio actually picks up
    summary.add_row("", "")
    mean_spread = r.get("mean_spread")
    ann_spread = r.get("annualized_spread")
    spread_t = r.get("t_stat_spread")
    spread_hit = r.get("hit_rate_spread")

    if mean_spread is None:
        summary.add_row("Top-Bottom quintile spread (monthly)", "[dim]n/a[/dim]")
    else:
        sp_color = "green" if mean_spread > 0 else "red"
        summary.add_row(
            "Top-Bottom quintile spread (monthly)",
            f"[{sp_color}]{mean_spread*100:+.2f}%[/{sp_color}]",
        )
    if ann_spread is not None:
        ann_color = "green" if ann_spread > 0 else "red"
        summary.add_row("Quintile spread (annualized)", f"[{ann_color}]{ann_spread*100:+.1f}%[/{ann_color}]")
    if spread_hit is not None:
        h_color = "green" if spread_hit > 0.5 else "yellow"
        summary.add_row("Spread hit rate (% periods spread > 0)", f"[{h_color}]{spread_hit*100:.0f}%[/{h_color}]")
    if spread_t is not None:
        t_color = "green" if abs(spread_t) >= 3.0 else "yellow" if abs(spread_t) >= 2.0 else "red"
        summary.add_row("t-stat (H0: mean spread = 0)", f"[{t_color}]{spread_t:+.2f}[/{t_color}]")

    console.print(summary)

    console.print(
        "\n[dim]Reference values:[/dim]\n"
        "[dim]  IC       ~0.02-0.05 mean = decent · IR >0.5 = useful · t-stat ≥3.0 = Harvey/Liu/Zhu bar[/dim]\n"
        "[dim]  Spread   monthly top-bottom gap. Annualized 5-15% on robust factors. Backtest top-N [/dim]\n"
        "[dim]           selection cares more about this right-tail-vs-left-tail metric than full-IC.[/dim]"
    )


def run_sweep(
    universe_names: list[str],
    signal_name: str,
    lookback_months: int,
    benchmark_ticker: str,
    concurrency: int,
) -> dict[str, dict]:
    """Run IC analysis across several universes and print a comparison."""
    console.print(Panel(
        f"[bold cyan]🔁 IC sweep[/bold cyan]\n"
        f"Signal: {signal_name} | Universes: {', '.join(universe_names)} | "
        f"{lookback_months} months",
        expand=False,
    ))

    results: dict[str, dict] = {}
    for name in universe_names:
        console.print(f"\n[bold]── {name} ──[/bold]")
        r = run_ic(
            tickers=UNIVERSES[name],
            signal_name=signal_name,
            lookback_months=lookback_months,
            benchmark_ticker=benchmark_ticker,
            concurrency=concurrency,
            label=name,
            verbose=False,
        )
        if r:
            results[name] = r
            mean_ic = r["mean_ic"]
            ir = r["ir"]
            hit = r["hit_rate"]
            t_stat = r["t_stat"]
            spread = r.get("mean_spread")
            ann_sp = r.get("annualized_spread")
            if mean_ic is not None and ir is not None and hit is not None and t_stat is not None:
                line = (
                    f"  Mean IC: {mean_ic:+.4f}  IR: {ir:+.2f}  "
                    f"hit: {hit*100:.0f}%  t: {t_stat:+.2f}"
                )
                if spread is not None and ann_sp is not None:
                    line += f"  | spread {spread*100:+.2f}%/mo (ann {ann_sp*100:+.1f}%)"
                line += f"  ({r['n_periods']} periods)"
                console.print(line)
            else:
                console.print("  [dim]insufficient data[/dim]")
        else:
            console.print("  [red]No result[/red]")

    if not results:
        return results

    table = Table(title="IC sweep summary", border_style="cyan")
    table.add_column("Universe", style="bold")
    table.add_column("Mean IC", justify="right")
    table.add_column("IR", justify="right")
    table.add_column("Hit", justify="right")
    table.add_column("t-IC", justify="right")
    table.add_column("Spread/mo", justify="right")
    table.add_column("Spread (ann)", justify="right")
    table.add_column("t-Sp", justify="right")
    table.add_column("Periods", justify="right")

    def _sort_key(kv):
        sp = kv[1].get("annualized_spread")
        return sp if sp is not None else float("-inf")

    for name, r in sorted(results.items(), key=_sort_key, reverse=True):
        mean_ic = r["mean_ic"]
        ir = r["ir"]
        hit = r["hit_rate"]
        t_stat = r["t_stat"]
        spread = r.get("mean_spread")
        ann_sp = r.get("annualized_spread")
        t_sp = r.get("t_stat_spread")
        if mean_ic is None:
            table.add_row(name, "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", str(r["n_periods"]))
            continue
        ic_color = "green" if mean_ic > 0 else "red"
        hit_color = "green" if hit > 0.5 else "yellow"
        t_color = "green" if abs(t_stat) >= 3.0 else "yellow" if abs(t_stat) >= 2.0 else "red"
        sp_color = "green" if (spread or 0) > 0 else "red"
        ann_color = "green" if (ann_sp or 0) > 0 else "red"
        tsp_color = (
            "green" if t_sp is not None and abs(t_sp) >= 3.0
            else "yellow" if t_sp is not None and abs(t_sp) >= 2.0 else "red"
        )
        table.add_row(
            name,
            f"[{ic_color}]{mean_ic:+.4f}[/{ic_color}]",
            f"{ir:+.2f}",
            f"[{hit_color}]{hit*100:.0f}%[/{hit_color}]",
            f"[{t_color}]{t_stat:+.2f}[/{t_color}]",
            "n/a" if spread is None else f"[{sp_color}]{spread*100:+.2f}%[/{sp_color}]",
            "n/a" if ann_sp is None else f"[{ann_color}]{ann_sp*100:+.1f}%[/{ann_color}]",
            "n/a" if t_sp is None else f"[{tsp_color}]{t_sp:+.2f}[/{tsp_color}]",
            str(r["n_periods"]),
        )
    console.print()
    console.print(table)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Information Coefficient analysis for a signal")
    parser.add_argument("--universe", choices=list(UNIVERSES.keys()) + ["ALL"], default="US_LARGE",
                        help="Universe to analyze")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (overrides --universe)")
    parser.add_argument("--signal", choices=list(SIGNAL_FNS.keys()), default="composite",
                        help="Which signal to test (default: composite)")
    parser.add_argument("--months", type=int, default=BACKTEST["default_lookback_months"],
                        help=f"Lookback in months (default {BACKTEST['default_lookback_months']})")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker for relative-strength (default SPY)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Max concurrent Yahoo API calls (default 5)")
    parser.add_argument("--sweep", nargs="*", default=None,
                        help=f"Run across multiple universes. Empty = config default "
                             f"({', '.join(BACKTEST['sweep_universes'])}).")
    args = parser.parse_args()

    if args.sweep is not None:
        names = args.sweep if args.sweep else BACKTEST["sweep_universes"]
        invalid = [n for n in names if n not in UNIVERSES]
        if invalid:
            console.print(f"[red]Unknown universe(s): {', '.join(invalid)}[/red]")
            sys.exit(1)
        run_sweep(
            universe_names=names,
            signal_name=args.signal,
            lookback_months=args.months,
            benchmark_ticker=args.benchmark,
            concurrency=args.concurrency,
        )
    else:
        if args.tickers:
            tickers = [t.upper() for t in args.tickers]
            label = "Custom tickers"
        elif args.universe == "ALL":
            tickers = ALL_TICKERS
            label = "ALL"
        else:
            tickers = UNIVERSES[args.universe]
            label = args.universe

        run_ic(
            tickers=tickers,
            signal_name=args.signal,
            lookback_months=args.months,
            benchmark_ticker=args.benchmark,
            concurrency=args.concurrency,
            label=label,
        )
