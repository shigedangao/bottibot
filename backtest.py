# backtest.py — Monthly rebalance backtest vs SPY buy-and-hold
#
# Technical-only backtest (no fundamentals) to avoid look-ahead bias.
# Simulates: each month, buy the top-N stocks ranked by technical score,
# hold for one month, rebalance. Compare to SPY buy-and-hold.

import argparse
import sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ALL_TICKERS, UNIVERSES, SCORING_WEIGHTS
from data.fetcher import fetch_ohlcv
from analysis.technical import compute_indicators, get_technical_signals

console = Console()


def _technical_score(tech_signals: dict) -> float:
    """
    Compute a technical-only score (0-100) using only the technical components
    of the scoring engine. Used for backtesting to avoid fundamentals look-ahead.
    Weights are rescaled from SCORING_WEIGHTS after dropping fundamental/quality.
    """
    w = SCORING_WEIGHTS
    tech_total = w["momentum"] + w["trend"] + w["rsi"] + w["volume"]

    abs_momentum = tech_signals.get("momentum_score", 0.5)
    rel_strength = tech_signals.get("relative_strength_score", 0.5)
    momentum = abs_momentum * 0.6 + rel_strength * 0.4

    raw = (
        momentum                              * w["momentum"] +
        tech_signals.get("trend_score", 0.5)  * w["trend"] +
        tech_signals.get("rsi_score", 0.5)    * w["rsi"] +
        tech_signals.get("volume_score", 0.5) * w["volume"]
    ) / tech_total

    if tech_signals.get("ema_aligned") and tech_signals.get("macd_bullish"):
        raw += 0.05

    return min(100.0, raw * 100)


def _score_at_date(full_df: pd.DataFrame, benchmark_slice: pd.DataFrame, as_of_idx: int) -> Optional[float]:
    """
    Score a ticker using only data available up to as_of_idx.
    Returns None if insufficient history.
    """
    if as_of_idx < 200:  # need at least ~200 days for EMA200
        return None

    df_slice = full_df.iloc[:as_of_idx + 1].copy()
    try:
        df_ind = compute_indicators(df_slice)
        signals = get_technical_signals(df_ind, benchmark_df=benchmark_slice)
        if not signals:
            return None
        return _technical_score(signals)
    except Exception:
        return None


def _get_rebalance_dates(bench_index: pd.DatetimeIndex, lookback_months: int) -> list[pd.Timestamp]:
    """
    Return a list of rebalance dates — the first trading day of each month
    within the lookback window.
    """
    end = bench_index[-1]
    start = end - pd.DateOffset(months=lookback_months)
    # Build monthly period range, then find first trading day in each period
    months = pd.date_range(start=start, end=end, freq="MS")
    dates = []
    for m in months:
        # First trading day >= month start
        mask = bench_index >= m
        if mask.any():
            dates.append(bench_index[mask][0])
    # Deduplicate and sort
    return sorted(set(dates))


def run_backtest(
    tickers: list[str],
    lookback_months: int = 24,
    top_n: int = 5,
    benchmark_ticker: str = "SPY",
    concurrency: int = 5,
) -> dict:
    """
    Run a monthly-rebalance backtest.
    Returns dict with portfolio returns per period and aggregate stats.
    """
    console.print(Panel(
        f"[bold cyan]📊 Backtest[/bold cyan]\n"
        f"Universe: {len(tickers)} tickers | Hold top {top_n} | Lookback: {lookback_months} months",
        expand=False,
    ))

    # Fetch 3+ years of history (enough for lookback + EMA200 warmup)
    period = "5y" if lookback_months >= 24 else "3y"

    console.print(f"[dim]Fetching {benchmark_ticker} benchmark...[/dim]")
    bench_df = fetch_ohlcv(benchmark_ticker, period=period)
    if bench_df is None or len(bench_df) < 252:
        console.print("[red]Failed to fetch benchmark data[/red]")
        return {}
    bench_df.index = bench_df.index.tz_localize(None) if bench_df.index.tz else bench_df.index

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
            print(f"\r  [{completed}/{len(tickers)}] {t:<12}", end="", flush=True)
            if df is not None:
                ticker_dfs[t] = df
    print(f"\r  ✓ {len(ticker_dfs)}/{len(tickers)} tickers loaded with sufficient history           ")

    if not ticker_dfs:
        console.print("[red]No tickers loaded[/red]")
        return {}

    rebalance_dates = _get_rebalance_dates(bench_df.index, lookback_months)
    if len(rebalance_dates) < 2:
        console.print("[red]Not enough rebalance dates[/red]")
        return {}

    console.print(f"[dim]Running {len(rebalance_dates) - 1} rebalance periods...[/dim]\n")

    periods = []
    portfolio_value = 1.0
    bench_value = 1.0
    bench_start_price = None

    for period_idx in range(len(rebalance_dates) - 1):
        entry_date = rebalance_dates[period_idx]
        exit_date = rebalance_dates[period_idx + 1]

        # Score each ticker as of entry_date
        bench_entry_idx = bench_df.index.get_indexer([entry_date], method="nearest")[0]
        bench_slice = bench_df.iloc[:bench_entry_idx + 1]

        scored: list[tuple[str, float, float, float]] = []  # (ticker, score, entry_price, exit_price)
        for ticker, df in ticker_dfs.items():
            # Align entry date to this ticker's trading days
            entry_idx_arr = df.index.get_indexer([entry_date], method="nearest")
            exit_idx_arr = df.index.get_indexer([exit_date], method="nearest")
            if len(entry_idx_arr) == 0 or len(exit_idx_arr) == 0:
                continue
            entry_idx = entry_idx_arr[0]
            exit_idx = exit_idx_arr[0]

            score = _score_at_date(df, bench_slice, entry_idx)
            if score is None:
                continue

            entry_price = df["close"].iloc[entry_idx]
            exit_price = df["close"].iloc[exit_idx]
            scored.append((ticker, score, entry_price, exit_price))

        if not scored:
            continue

        # Pick top N
        scored.sort(key=lambda x: x[1], reverse=True)
        picks = scored[:top_n]

        # Equal-weight portfolio return for this period
        returns = [(p[3] / p[2] - 1) for p in picks if p[2] > 0]
        if not returns:
            continue
        period_return = float(np.mean(returns))

        # Benchmark return for same period
        bench_entry = bench_df["close"].iloc[bench_entry_idx]
        bench_exit_idx = bench_df.index.get_indexer([exit_date], method="nearest")[0]
        bench_exit = bench_df["close"].iloc[bench_exit_idx]
        bench_period_return = float(bench_exit / bench_entry - 1)

        portfolio_value *= (1 + period_return)
        bench_value *= (1 + bench_period_return)

        periods.append({
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "picks": [p[0] for p in picks],
            "portfolio_return": period_return,
            "benchmark_return": bench_period_return,
            "portfolio_value": portfolio_value,
            "benchmark_value": bench_value,
            "excess": period_return - bench_period_return,
        })

    if not periods:
        console.print("[red]No valid periods in backtest[/red]")
        return {}

    # Aggregate stats
    portfolio_returns = np.array([p["portfolio_return"] for p in periods])
    benchmark_returns = np.array([p["benchmark_return"] for p in periods])
    excess_returns = portfolio_returns - benchmark_returns

    n_periods = len(periods)
    years = n_periods / 12.0

    total_return = portfolio_value - 1
    bench_total = bench_value - 1
    cagr = (portfolio_value ** (1 / years) - 1) if years > 0 else 0
    bench_cagr = (bench_value ** (1 / years) - 1) if years > 0 else 0

    # Sharpe ratio (monthly, annualized, rf=0)
    if portfolio_returns.std() > 0:
        sharpe = (portfolio_returns.mean() / portfolio_returns.std()) * np.sqrt(12)
    else:
        sharpe = 0.0
    if benchmark_returns.std() > 0:
        bench_sharpe = (benchmark_returns.mean() / benchmark_returns.std()) * np.sqrt(12)
    else:
        bench_sharpe = 0.0

    # Max drawdown
    def _max_drawdown(cum_values: list[float]) -> float:
        peak = cum_values[0]
        mdd = 0.0
        for v in cum_values:
            peak = max(peak, v)
            dd = (v / peak - 1) if peak > 0 else 0
            mdd = min(mdd, dd)
        return mdd

    portfolio_curve = [p["portfolio_value"] for p in periods]
    benchmark_curve = [p["benchmark_value"] for p in periods]
    max_dd = _max_drawdown(portfolio_curve)
    bench_max_dd = _max_drawdown(benchmark_curve)

    # Win rate (beating benchmark)
    win_rate = float((excess_returns > 0).mean())

    results = {
        "n_periods": n_periods,
        "years": round(years, 2),
        "total_return": total_return,
        "cagr": cagr,
        "benchmark_total_return": bench_total,
        "benchmark_cagr": bench_cagr,
        "alpha": cagr - bench_cagr,
        "sharpe": sharpe,
        "benchmark_sharpe": bench_sharpe,
        "max_drawdown": max_dd,
        "benchmark_max_drawdown": bench_max_dd,
        "win_rate": win_rate,
        "avg_monthly_return": float(portfolio_returns.mean()),
        "avg_monthly_excess": float(excess_returns.mean()),
        "periods": periods,
    }

    _print_results(results)
    return results


def _print_results(r: dict):
    """Print backtest summary."""
    # Period-by-period table
    table = Table(title="Monthly Periods", border_style="bright_black")
    table.add_column("Entry", style="dim")
    table.add_column("Exit", style="dim")
    table.add_column("Picks", no_wrap=False, max_width=40)
    table.add_column("Portfolio", justify="right")
    table.add_column("SPY", justify="right")
    table.add_column("Excess", justify="right")

    for p in r["periods"][-12:]:  # show last 12 periods
        port_ret = p["portfolio_return"] * 100
        bench_ret = p["benchmark_return"] * 100
        excess = p["excess"] * 100

        port_c = "green" if port_ret >= 0 else "red"
        excess_c = "green" if excess >= 0 else "red"

        table.add_row(
            p["entry_date"],
            p["exit_date"],
            ", ".join(p["picks"]),
            f"[{port_c}]{port_ret:+.2f}%[/{port_c}]",
            f"{bench_ret:+.2f}%",
            f"[{excess_c}]{excess:+.2f}%[/{excess_c}]",
        )

    console.print(table)
    if len(r["periods"]) > 12:
        console.print(f"[dim](showing last 12 of {len(r['periods'])} periods)[/dim]\n")

    # Summary
    alpha_color = "green" if r["alpha"] > 0 else "red"
    win_color = "green" if r["win_rate"] > 0.5 else "yellow"

    summary = Table(title="Backtest Summary", show_header=False, border_style="cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Strategy", justify="right")
    summary.add_column("SPY", justify="right")

    summary.add_row("Period", f"{r['years']:.1f} years ({r['n_periods']} months)", "")
    summary.add_row("Total Return", f"{r['total_return']*100:+.1f}%", f"{r['benchmark_total_return']*100:+.1f}%")
    summary.add_row("CAGR", f"{r['cagr']*100:+.1f}%", f"{r['benchmark_cagr']*100:+.1f}%")
    summary.add_row("Alpha (CAGR)", f"[{alpha_color}]{r['alpha']*100:+.1f}%[/{alpha_color}]", "—")
    summary.add_row("Sharpe Ratio", f"{r['sharpe']:.2f}", f"{r['benchmark_sharpe']:.2f}")
    summary.add_row("Max Drawdown", f"{r['max_drawdown']*100:.1f}%", f"{r['benchmark_max_drawdown']*100:.1f}%")
    summary.add_row("Win Rate vs SPY", f"[{win_color}]{r['win_rate']*100:.0f}%[/{win_color}]", "—")
    summary.add_row("Avg Monthly Return", f"{r['avg_monthly_return']*100:+.2f}%", "")
    summary.add_row("Avg Monthly Excess", f"{r['avg_monthly_excess']*100:+.2f}%", "")

    console.print(summary)

    # Verdict
    if r["alpha"] > 0.02 and r["win_rate"] > 0.55:
        console.print("\n[bold green]✅ Strategy shows meaningful edge over SPY[/bold green]")
    elif r["alpha"] > 0:
        console.print("\n[bold yellow]⚠️ Strategy slightly outperforms — edge is weak[/bold yellow]")
    else:
        console.print("\n[bold red]❌ Strategy underperforms SPY — review scoring[/bold red]")

    console.print(
        "\n[dim]Note: Technical-only backtest (fundamentals excluded to avoid look-ahead bias).[/dim]\n"
        "[dim]Survivorship bias: universe uses current tickers, ignores delisted names.[/dim]"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest the scoring strategy vs SPY")
    parser.add_argument("--universe", choices=list(UNIVERSES.keys()) + ["ALL"], default="US_LARGE",
                        help="Universe of stocks to backtest")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (overrides --universe)")
    parser.add_argument("--months", type=int, default=24, help="Lookback in months (default 24)")
    parser.add_argument("--top", type=int, default=5, help="Top N stocks to hold each month")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker (default SPY)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Max concurrent Yahoo API calls when fetching history (default 5)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.universe == "ALL":
        tickers = ALL_TICKERS
    else:
        tickers = UNIVERSES[args.universe]

    run_backtest(
        tickers=tickers,
        lookback_months=args.months,
        top_n=args.top,
        benchmark_ticker=args.benchmark,
        concurrency=args.concurrency,
    )
