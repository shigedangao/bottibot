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

from config import ALL_TICKERS, UNIVERSES, SCORING_WEIGHTS, BACKTEST
from data.fetcher import fetch_ohlcv
from analysis.technical import compute_indicators, get_technical_signals
from analysis.stats import (
    bootstrap_ci, bootstrap_pairs_ci, deflated_sharpe_ratio,
    cagr as cagr_fn, sharpe as sharpe_fn, cagr_diff,
)

console = Console()


def _deploy_verdict(r: dict) -> tuple[str, str, list[str]]:
    """
    Multi-criteria readout: STRONG / OK / WEAK / NO.
    Based on net alpha, Sharpe, win rate, and max drawdown.
    Returns (label, rich-color, failing-criteria).
    NOT a buy recommendation — just a structured summary of historical edge.
    """
    thr = BACKTEST["deploy_thresholds"]
    alpha = r["alpha_net"]

    if alpha <= 0:
        return "NO", "red", ["negative net alpha"]

    def _check(t: dict) -> list[str]:
        fails = []
        if alpha < t["alpha_net"]:
            fails.append(f"alpha {alpha*100:+.1f}% < {t['alpha_net']*100:.1f}%")
        if r["sharpe"] < t["sharpe"]:
            fails.append(f"sharpe {r['sharpe']:.2f} < {t['sharpe']:.2f}")
        if r["win_rate"] < t["win_rate"]:
            fails.append(f"win rate {r['win_rate']*100:.0f}% < {t['win_rate']*100:.0f}%")
        if r["max_drawdown"] < t["max_drawdown_floor"]:
            fails.append(f"MDD {r['max_drawdown']*100:.0f}% < {t['max_drawdown_floor']*100:.0f}%")
        return fails

    strong_fails = _check(thr["strong"])
    if not strong_fails:
        return "STRONG", "bright_green", []

    ok_fails = _check(thr["ok"])
    if not ok_fails:
        return "OK", "green", []

    return "WEAK", "yellow", ok_fails


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
    cost_per_side_bps: float | None = None,
    stickiness_bonus_pts: float | None = None,
    regime_filter: bool | None = None,
    label: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Run a monthly-rebalance backtest.
    Returns dict with portfolio returns per period and aggregate stats.
    Applies a per-side transaction cost (commission + slippage) on each rebalance,
    proportional to actual turnover. Stickiness gives currently-held positions
    a score bonus during sorting so a challenger must beat them by that gap to
    take their slot — reduces churn. Regime filter forces cash when the
    benchmark trades below its long moving average.
    """
    if cost_per_side_bps is None:
        cost_per_side_bps = BACKTEST["cost_per_side_bps"]
    if stickiness_bonus_pts is None:
        stickiness_bonus_pts = BACKTEST["stickiness_bonus_pts"]
    if regime_filter is None:
        regime_filter = BACKTEST["regime_filter_enabled"]
    regime_ma_window = BACKTEST["regime_ma_window"]

    if verbose:
        title = label or "Backtest"
        regime_line = (
            f"Regime filter: cash when {benchmark_ticker} < {regime_ma_window}d MA"
            if regime_filter else "Regime filter: OFF"
        )
        console.print(Panel(
            f"[bold cyan]📊 {title}[/bold cyan]\n"
            f"Universe: {len(tickers)} tickers | Hold top {top_n} | Lookback: {lookback_months} months\n"
            f"Cost: {cost_per_side_bps:.0f} bps/side ({cost_per_side_bps*2:.0f} bps round-trip on full rotation)\n"
            f"Stickiness: +{stickiness_bonus_pts:.1f} pts to currently-held positions\n"
            f"{regime_line}",
            expand=False,
        ))

    # Fetch enough history for lookback + EMA200 warmup
    if lookback_months >= 48:
        period = "10y"
    elif lookback_months >= 24:
        period = "5y"
    else:
        period = "3y"

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
        if verbose:
            console.print("[red]No tickers loaded[/red]")
        return {}

    rebalance_dates = _get_rebalance_dates(bench_df.index, lookback_months)
    if len(rebalance_dates) < 2:
        if verbose:
            console.print("[red]Not enough rebalance dates[/red]")
        return {}

    if verbose:
        console.print(f"[dim]Running {len(rebalance_dates) - 1} rebalance periods...[/dim]\n")

    periods = []
    portfolio_value_gross = 1.0
    portfolio_value_net = 1.0
    bench_value = 1.0
    prev_picks: set[str] = set()

    for period_idx in range(len(rebalance_dates) - 1):
        entry_date = rebalance_dates[period_idx]
        exit_date = rebalance_dates[period_idx + 1]

        # Score each ticker as of entry_date
        bench_entry_idx = bench_df.index.get_indexer([entry_date], method="nearest")[0]
        bench_slice = bench_df.iloc[:bench_entry_idx + 1]

        # Regime check: if SPY trades below its long MA, force cash this period.
        regime_risk_off = False
        if regime_filter and len(bench_slice) >= regime_ma_window:
            ma_long = bench_slice["close"].iloc[-regime_ma_window:].mean()
            regime_risk_off = bench_slice["close"].iloc[-1] < ma_long

        scored: list[tuple[str, float, float, float]] = []  # (ticker, score, entry_price, exit_price)
        for ticker, df in ticker_dfs.items():
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

        if not scored and not regime_risk_off:
            continue

        # Pick top N — currently-held positions get a stickiness bonus so a
        # challenger must beat them by more than `stickiness_bonus_pts` to displace.
        # When regime_risk_off, picks = [] (full cash).
        if regime_risk_off:
            picks: list[tuple[str, float, float, float]] = []
            period_return_gross = 0.0
        else:
            def _adjusted(item: tuple) -> float:
                return item[1] + (stickiness_bonus_pts if item[0] in prev_picks else 0.0)
            scored.sort(key=_adjusted, reverse=True)
            picks = scored[:top_n]

            returns = [(p[3] / p[2] - 1) for p in picks if p[2] > 0]
            if not returns:
                continue
            period_return_gross = float(np.mean(returns))

        # Transaction cost on actual changes between previous and new holdings.
        # Generalized formula handles all transitions (initial buy, normal rebalance,
        # going to cash, coming back from cash). top_n is the equal-weight denominator.
        new_picks = set(p[0] for p in picks)
        n_added   = len(new_picks - prev_picks)
        n_removed = len(prev_picks - new_picks)
        buy_fraction  = n_added   / top_n
        sell_fraction = n_removed / top_n
        cost = (buy_fraction + sell_fraction) * cost_per_side_bps / 10_000.0
        period_return_net = period_return_gross - cost
        prev_picks = new_picks

        # Benchmark return for same period
        bench_entry = bench_df["close"].iloc[bench_entry_idx]
        bench_exit_idx = bench_df.index.get_indexer([exit_date], method="nearest")[0]
        bench_exit = bench_df["close"].iloc[bench_exit_idx]
        bench_period_return = float(bench_exit / bench_entry - 1)

        portfolio_value_gross *= (1 + period_return_gross)
        portfolio_value_net *= (1 + period_return_net)
        bench_value *= (1 + bench_period_return)

        periods.append({
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "picks": [p[0] for p in picks] if picks else ["CASH"],
            "regime": "RISK_OFF" if regime_risk_off else "RISK_ON",
            "portfolio_return_gross": period_return_gross,
            "portfolio_return_net":   period_return_net,
            "cost":                   cost,
            "turnover":               (buy_fraction + sell_fraction) / 2.0,
            "benchmark_return":       bench_period_return,
            "portfolio_value_net":    portfolio_value_net,
            "benchmark_value":        bench_value,
            "excess_net":             period_return_net - bench_period_return,
        })

    if not periods:
        if verbose:
            console.print("[red]No valid periods in backtest[/red]")
        return {}

    # Aggregate stats
    returns_gross = np.array([p["portfolio_return_gross"] for p in periods])
    returns_net   = np.array([p["portfolio_return_net"]   for p in periods])
    benchmark_returns = np.array([p["benchmark_return"] for p in periods])
    excess_returns_net = returns_net - benchmark_returns
    turnovers = np.array([p["turnover"] for p in periods])

    n_periods = len(periods)
    years = n_periods / 12.0

    total_return_gross = portfolio_value_gross - 1
    total_return_net   = portfolio_value_net - 1
    bench_total = bench_value - 1
    cagr_gross = (portfolio_value_gross ** (1 / years) - 1) if years > 0 else 0
    cagr_net   = (portfolio_value_net   ** (1 / years) - 1) if years > 0 else 0
    bench_cagr = (bench_value ** (1 / years) - 1) if years > 0 else 0

    # Sharpe ratio (monthly, annualized, rf=0) — computed on net returns
    if returns_net.std() > 0:
        sharpe = (returns_net.mean() / returns_net.std()) * np.sqrt(12)
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

    portfolio_curve = [p["portfolio_value_net"] for p in periods]
    benchmark_curve = [p["benchmark_value"] for p in periods]
    max_dd = _max_drawdown(portfolio_curve)
    bench_max_dd = _max_drawdown(benchmark_curve)

    # Win rate (beating benchmark, net of costs)
    win_rate = float((excess_returns_net > 0).mean())

    # Regime stats
    n_cash_periods = sum(1 for p in periods if p.get("regime") == "RISK_OFF")
    pct_in_cash = n_cash_periods / n_periods if n_periods else 0.0

    # ── Statistical hygiene: bootstrap CIs + Deflated Sharpe ──────────────
    # Bootstrap on the net return series. Block bootstrap would be more
    # correct (preserves any serial dependence) but for small T (~60) the
    # gain over IID resampling is mild — keeping it simple.
    n_boot = BACKTEST.get("n_boot", 1000)
    ci_level = BACKTEST.get("bootstrap_ci", 0.95)
    n_trials = BACKTEST.get("n_trials_for_dsr", 1)

    cagr_pt, cagr_lo, cagr_hi     = bootstrap_ci(returns_net, cagr_fn, n_boot, ci_level)
    sharpe_pt, sharpe_lo, sharpe_hi = bootstrap_ci(returns_net, sharpe_fn, n_boot, ci_level)
    alpha_pt, alpha_lo, alpha_hi   = bootstrap_pairs_ci(returns_net, benchmark_returns, cagr_diff, n_boot, ci_level)

    dsr_stats = deflated_sharpe_ratio(returns_net, n_trials=n_trials, periods_per_year=12)

    results = {
        "label":                  label or "Backtest",
        "n_periods":              n_periods,
        "years":                  round(years, 2),
        "cost_per_side_bps":      cost_per_side_bps,
        "stickiness_bonus_pts":   stickiness_bonus_pts,
        "regime_filter":          regime_filter,
        "pct_in_cash":            pct_in_cash,
        "total_return_gross":     total_return_gross,
        "total_return_net":       total_return_net,
        "cagr_gross":             cagr_gross,
        "cagr_net":               cagr_net,
        "cost_drag_cagr":         cagr_gross - cagr_net,
        "benchmark_total_return": bench_total,
        "benchmark_cagr":         bench_cagr,
        "alpha_gross":            cagr_gross - bench_cagr,
        "alpha_net":              cagr_net   - bench_cagr,
        "sharpe":                 sharpe,
        "benchmark_sharpe":       bench_sharpe,
        "max_drawdown":           max_dd,
        "benchmark_max_drawdown": bench_max_dd,
        "win_rate":               win_rate,
        "avg_turnover":           float(turnovers.mean()),
        "avg_monthly_return_net": float(returns_net.mean()),
        "avg_monthly_excess_net": float(excess_returns_net.mean()),
        "periods":                periods,
        # Statistical hygiene
        "cagr_net_ci":            (cagr_lo, cagr_hi),
        "sharpe_ci":              (sharpe_lo, sharpe_hi),
        "alpha_net_ci":           (alpha_lo, alpha_hi),
        "psr_zero":               dsr_stats["psr_zero"],
        "dsr":                    dsr_stats["dsr"],
        "sr_threshold_ann":       dsr_stats["sr_threshold_ann"],
        "skew":                   dsr_stats["skew"],
        "excess_kurtosis":        dsr_stats["excess_kurtosis"],
        "n_trials":               n_trials,
    }

    if verbose:
        _print_results(results)
    return results


def _print_results(r: dict):
    """Print backtest summary."""
    # Period-by-period table
    table = Table(title="Monthly Periods (net of costs)", border_style="bright_black")
    table.add_column("Entry", style="dim")
    table.add_column("Exit", style="dim")
    table.add_column("Picks", no_wrap=False, max_width=40)
    table.add_column("Portfolio", justify="right")
    table.add_column("SPY", justify="right")
    table.add_column("Excess", justify="right")
    table.add_column("Turn.", justify="right")

    for p in r["periods"][-12:]:
        port_ret = p["portfolio_return_net"] * 100
        bench_ret = p["benchmark_return"] * 100
        excess = p["excess_net"] * 100

        port_c = "green" if port_ret >= 0 else "red"
        excess_c = "green" if excess >= 0 else "red"

        table.add_row(
            p["entry_date"],
            p["exit_date"],
            ", ".join(p["picks"]),
            f"[{port_c}]{port_ret:+.2f}%[/{port_c}]",
            f"{bench_ret:+.2f}%",
            f"[{excess_c}]{excess:+.2f}%[/{excess_c}]",
            f"{p['turnover']*100:.0f}%",
        )

    console.print(table)
    if len(r["periods"]) > 12:
        console.print(f"[dim](showing last 12 of {len(r['periods'])} periods)[/dim]\n")

    # Summary
    alpha_net = r["alpha_net"]
    alpha_color = "green" if alpha_net > 0 else "red"
    win_color = "green" if r["win_rate"] > 0.5 else "yellow"

    summary = Table(title="Backtest Summary", show_header=False, border_style="cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Strategy", justify="right")
    summary.add_column("SPY", justify="right")

    summary.add_row("Period", f"{r['years']:.1f} years ({r['n_periods']} months)", "")
    summary.add_row("Total Return (net)",  f"{r['total_return_net']*100:+.1f}%",  f"{r['benchmark_total_return']*100:+.1f}%")
    summary.add_row("CAGR (gross)",        f"{r['cagr_gross']*100:+.1f}%",        "")

    cagr_lo, cagr_hi = r["cagr_net_ci"]
    summary.add_row(
        "CAGR (net) [95% CI]",
        f"{r['cagr_net']*100:+.1f}% [{cagr_lo*100:+.1f}, {cagr_hi*100:+.1f}]",
        f"{r['benchmark_cagr']*100:+.1f}%",
    )
    summary.add_row("Cost drag (CAGR)",    f"−{r['cost_drag_cagr']*100:.2f}%",    "—")
    summary.add_row("Alpha gross",         f"{r['alpha_gross']*100:+.1f}%",       "—")

    alpha_lo, alpha_hi = r["alpha_net_ci"]
    spans_zero = alpha_lo <= 0 <= alpha_hi
    alpha_ci_color = "yellow" if spans_zero else alpha_color
    summary.add_row(
        "Alpha net [95% CI]",
        f"[{alpha_ci_color}]{alpha_net*100:+.1f}% [{alpha_lo*100:+.1f}, {alpha_hi*100:+.1f}][/{alpha_ci_color}]",
        "—",
    )
    sharpe_lo, sharpe_hi = r["sharpe_ci"]
    summary.add_row(
        "Sharpe (net) [95% CI]",
        f"{r['sharpe']:.2f} [{sharpe_lo:+.2f}, {sharpe_hi:+.2f}]",
        f"{r['benchmark_sharpe']:.2f}",
    )
    summary.add_row("Max Drawdown",        f"{r['max_drawdown']*100:.1f}%",       f"{r['benchmark_max_drawdown']*100:.1f}%")
    summary.add_row("Win Rate vs SPY",     f"[{win_color}]{r['win_rate']*100:.0f}%[/{win_color}]", "—")
    summary.add_row("Avg Turnover/mo",     f"{r['avg_turnover']*100:.0f}%",       "")
    summary.add_row("Cost / side",         f"{r['cost_per_side_bps']:.0f} bps",   "")
    summary.add_row("Stickiness",          f"+{r['stickiness_bonus_pts']:.1f} pts", "")
    summary.add_row("Regime filter",       f"{'ON' if r['regime_filter'] else 'OFF'}", "")
    summary.add_row("% time in cash",      f"{r['pct_in_cash']*100:.0f}%", "")

    # Deflated Sharpe block — the multiple-testing correction
    summary.add_row("", "", "")
    summary.add_row("Skew / Excess kurt",  f"{r['skew']:+.2f} / {r['excess_kurtosis']:+.2f}", "")

    psr_zero = r["psr_zero"]
    if psr_zero is not None:
        psr_color = "green" if psr_zero >= 0.95 else "yellow" if psr_zero >= 0.80 else "red"
        summary.add_row("PSR(0)",              f"[{psr_color}]{psr_zero*100:.1f}%[/{psr_color}]", "")

    sr_thresh = r["sr_threshold_ann"]
    if sr_thresh is not None:
        summary.add_row(
            f"Sharpe threshold (N={r['n_trials']} trials)",
            f"{sr_thresh:.2f}",
            "",
        )

    dsr = r["dsr"]
    if dsr is not None:
        dsr_color = "green" if dsr >= 0.95 else "yellow" if dsr >= 0.80 else "red"
        summary.add_row(
            "Deflated Sharpe Ratio (DSR)",
            f"[{dsr_color}]{dsr*100:.1f}%[/{dsr_color}]",
            "",
        )

    console.print(summary)

    # Multi-criteria verdict
    verdict, vcolor, fails = _deploy_verdict(r)
    icons = {"STRONG": "✅", "OK": "🟢", "WEAK": "⚠️", "NO": "❌"}
    icon = icons.get(verdict, "•")
    console.print(f"\n[bold {vcolor}]{icon} Deploy? {verdict}[/bold {vcolor}]")
    if fails:
        console.print(f"[dim]   Misses: {'; '.join(fails)}[/dim]")

    console.print(
        "\n[dim]Note: Technical-only backtest (fundamentals excluded to avoid look-ahead bias).[/dim]\n"
        "[dim]Survivorship bias: universe uses current tickers, ignores delisted names.[/dim]\n"
        "[dim]Deploy verdict is a structured historical readout — not financial advice.[/dim]"
    )


def run_sweep(
    universe_names: list[str],
    lookback_months: int,
    top_n: int,
    benchmark_ticker: str,
    concurrency: int,
    cost_per_side_bps: float,
    stickiness_bonus_pts: float,
    regime_filter: bool,
) -> dict[str, dict]:
    """Run the backtest across several universes and print a comparison."""
    console.print(Panel(
        f"[bold cyan]🔁 Backtest sweep[/bold cyan]\n"
        f"Universes: {', '.join(universe_names)}\n"
        f"Hold top {top_n} | {lookback_months} months | cost {cost_per_side_bps:.0f} bps/side | "
        f"stickiness +{stickiness_bonus_pts:.1f} pts | regime filter {'ON' if regime_filter else 'OFF'}",
        expand=False,
    ))

    results: dict[str, dict] = {}
    for name in universe_names:
        console.print(f"\n[bold]── {name} ──[/bold]")
        r = run_backtest(
            tickers=UNIVERSES[name],
            lookback_months=lookback_months,
            top_n=top_n,
            benchmark_ticker=benchmark_ticker,
            concurrency=concurrency,
            cost_per_side_bps=cost_per_side_bps,
            stickiness_bonus_pts=stickiness_bonus_pts,
            regime_filter=regime_filter,
            label=name,
            verbose=False,
        )
        if r:
            results[name] = r
            console.print(
                f"  CAGR net: {r['cagr_net']*100:+.1f}%  "
                f"vs SPY {r['benchmark_cagr']*100:+.1f}%  "
                f"alpha {r['alpha_net']*100:+.1f}%  "
                f"win {r['win_rate']*100:.0f}%  "
                f"turnover {r['avg_turnover']*100:.0f}%/mo  "
                f"cash {r['pct_in_cash']*100:.0f}%"
            )
        else:
            console.print(f"  [red]No result[/red]")

    if not results:
        return results

    # Comparison table
    table = Table(title="Sweep summary (net of costs)", border_style="cyan")
    table.add_column("Universe", style="bold")
    table.add_column("CAGR net", justify="right")
    table.add_column("Alpha", justify="right")
    table.add_column("Alpha 95% CI", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("DSR", justify="right")
    table.add_column("Win", justify="right")
    table.add_column("Turn", justify="right")
    table.add_column("Deploy?", justify="center")

    for name, r in sorted(results.items(), key=lambda kv: kv[1]["alpha_net"], reverse=True):
        alpha_color = "green" if r["alpha_net"] > 0 else "red"
        win_color = "green" if r["win_rate"] > 0.5 else "yellow"
        verdict, vcolor, _ = _deploy_verdict(r)
        alpha_lo, alpha_hi = r["alpha_net_ci"]
        ci_str = f"[{alpha_lo*100:+.1f}, {alpha_hi*100:+.1f}]"
        ci_color = "yellow" if alpha_lo <= 0 <= alpha_hi else alpha_color
        dsr = r.get("dsr")
        if dsr is None:
            dsr_str = "n/a"
        else:
            dsr_color = "green" if dsr >= 0.95 else "yellow" if dsr >= 0.80 else "red"
            dsr_str = f"[{dsr_color}]{dsr*100:.0f}%[/{dsr_color}]"
        table.add_row(
            name,
            f"{r['cagr_net']*100:+.1f}%",
            f"[{alpha_color}]{r['alpha_net']*100:+.1f}%[/{alpha_color}]",
            f"[{ci_color}]{ci_str}[/{ci_color}]",
            f"{r['sharpe']:.2f}",
            dsr_str,
            f"[{win_color}]{r['win_rate']*100:.0f}%[/{win_color}]",
            f"{r['avg_turnover']*100:.0f}%",
            f"[{vcolor}]{verdict}[/{vcolor}]",
        )
    console.print()
    console.print(table)

    n_wins = sum(1 for r in results.values() if r["alpha_net"] > 0)
    console.print(
        f"\n[bold]Net alpha verdict:[/bold] {n_wins}/{len(results)} universes beat SPY after costs"
    )
    console.print(
        "[dim]Deploy? legend — STRONG: alpha ≥5%, sharpe ≥0.70, win ≥45%, MDD ≥-40%."
        " OK: alpha ≥2%, sharpe ≥0.50, win ≥40%, MDD ≥-50%."
        " WEAK: positive alpha but fails OK criteria. NO: negative alpha.[/dim]"
    )
    console.print(
        "[dim]Not financial advice — historical readout only, with survivorship bias and ignoring regime changes.[/dim]"
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest the scoring strategy vs SPY (with transaction costs)")
    parser.add_argument("--universe", choices=list(UNIVERSES.keys()) + ["ALL"], default="US_LARGE",
                        help="Universe of stocks to backtest")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (overrides --universe)")
    parser.add_argument("--months", type=int, default=BACKTEST["default_lookback_months"],
                        help=f"Lookback in months (default {BACKTEST['default_lookback_months']})")
    parser.add_argument("--top", type=int, default=5, help="Top N stocks to hold each month")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker (default SPY)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Max concurrent Yahoo API calls when fetching history (default 5)")
    parser.add_argument("--cost-bps", type=float, default=BACKTEST["cost_per_side_bps"],
                        help=f"Per-side transaction cost in bps (default {BACKTEST['cost_per_side_bps']:.0f})")
    parser.add_argument("--stickiness", type=float, default=BACKTEST["stickiness_bonus_pts"],
                        help=f"Score bonus for currently-held positions during sort, in score points "
                             f"(default {BACKTEST['stickiness_bonus_pts']:.1f}). 0 = pure top-N every month.")
    parser.add_argument("--regime-filter", dest="regime_filter", action="store_true",
                        help=f"Enable the SPY {BACKTEST['regime_ma_window']}d MA regime filter "
                             f"(go to cash when SPY < MA). Off by default — see README for why.")
    parser.add_argument("--no-regime-filter", dest="regime_filter", action="store_false",
                        help="Disable the regime filter explicitly.")
    parser.set_defaults(regime_filter=BACKTEST["regime_filter_enabled"])
    parser.add_argument("--sweep", nargs="*", default=None,
                        help=f"Run across multiple universes. Empty = config default "
                             f"({', '.join(BACKTEST['sweep_universes'])}). "
                             f"Or pass names: --sweep US_LARGE EU_LARGE")
    args = parser.parse_args()

    if args.sweep is not None:
        names = args.sweep if args.sweep else BACKTEST["sweep_universes"]
        invalid = [n for n in names if n not in UNIVERSES]
        if invalid:
            console.print(f"[red]Unknown universe(s): {', '.join(invalid)}[/red]")
            sys.exit(1)
        run_sweep(
            universe_names=names,
            lookback_months=args.months,
            top_n=args.top,
            benchmark_ticker=args.benchmark,
            concurrency=args.concurrency,
            cost_per_side_bps=args.cost_bps,
            stickiness_bonus_pts=args.stickiness,
            regime_filter=args.regime_filter,
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

        run_backtest(
            tickers=tickers,
            lookback_months=args.months,
            top_n=args.top,
            benchmark_ticker=args.benchmark,
            concurrency=args.concurrency,
            cost_per_side_bps=args.cost_bps,
            stickiness_bonus_pts=args.stickiness,
            regime_filter=args.regime_filter,
            label=label,
        )
