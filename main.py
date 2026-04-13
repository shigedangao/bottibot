# main.py — Point d'entrée du Stock Analyzer

import json
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich import print as rprint

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ALL_TICKERS, UNIVERSES, DASHBOARD
from data.fetcher import fetch_ohlcv, fetch_fundamentals, fetch_vix, fetch_benchmark, fetch_earnings_date
from analysis.technical import compute_indicators, get_technical_signals
from analysis.fundamental import get_fundamental_signals, format_fundamentals_display
from scoring.engine import compute_final_score, rank_stocks

console = Console()


def analyze_ticker(
    ticker: str,
    vix_regime: str | None = None,
    benchmark_df=None,
) -> dict | None:
    """Analyse complète d'un ticker. Retourne None si impossible."""
    # 1. Données OHLCV
    df = fetch_ohlcv(ticker, period="1y")
    if df is None:
        return None

    # 2. Indicateurs techniques
    df = compute_indicators(df)
    tech_signals = get_technical_signals(df, benchmark_df=benchmark_df)
    if not tech_signals:
        return None

    # 3. Données fondamentales
    fundamentals = fetch_fundamentals(ticker)

    # 4. Signaux fondamentaux
    fund_signals = get_fundamental_signals(fundamentals)

    # 5. Score final (VIX-adjusted weights)
    score_result = compute_final_score(tech_signals, fund_signals, fundamentals, vix_regime)

    # 6. Earnings calendar
    earnings_date = fetch_earnings_date(ticker)
    earnings_soon = False
    if earnings_date:
        try:
            from datetime import date
            days_to_earnings = (date.fromisoformat(earnings_date) - date.today()).days
            earnings_soon = 0 <= days_to_earnings <= 7
        except (ValueError, TypeError):
            days_to_earnings = None
    else:
        days_to_earnings = None

    # Prix actuel
    current_price = df["close"].iloc[-1]

    return {
        "ticker":          ticker,
        "name":            fundamentals.get("name", ticker),
        "sector":          fundamentals.get("sector", "Unknown"),
        "currency":        fundamentals.get("currency", "USD"),
        "price":           round(current_price, 2),
        "score":           score_result["score"],
        "recommendation":  score_result["recommendation"],
        "emoji":           score_result["emoji"],
        "color":           score_result["color"],
        "reasons":         score_result["reasons"],
        # Signaux clés
        "momentum_10d":    round(tech_signals.get("momentum_10d", 0), 1),
        "momentum_60d":    round(tech_signals.get("momentum_60d", 0), 1),
        "rsi":             round(tech_signals.get("rsi_value", 50), 1),
        "volume_ratio":    round(tech_signals.get("volume_ratio", 1), 2),
        "ema_aligned":     tech_signals.get("ema_aligned", False),
        "adx":             round(tech_signals.get("adx", 20), 1),
        # Relative strength
        "excess_return_60d": tech_signals.get("excess_return_60d", 0.0),
        # Composantes du score
        "score_detail": {
            "momentum":    score_result["momentum_component"],
            "trend":       score_result["trend_component"],
            "rsi":         score_result["rsi_component"],
            "volume":      score_result["volume_component"],
            "fundamental": score_result["fundamental_component"],
            "quality":     score_result["quality_component"],
        },
        # Risk management
        "stop_loss_pct":    score_result["suggested_stop_loss"],
        "take_profit_pct":  score_result["suggested_take_profit"],
        "rr_ratio":         score_result["risk_reward_ratio"],
        # Earnings
        "earnings_date":    earnings_date,
        "earnings_soon":    earnings_soon,
        "days_to_earnings": days_to_earnings,
        # Fondamentaux formatés
        "fundamentals_display": format_fundamentals_display(fundamentals, fund_signals),
        # Timestamps
        "analyzed_at":     datetime.now().isoformat(),
    }


def run_screener(tickers: list[str] | None = None, top_n: int = None, max_per_sector: int = 0) -> list[dict]:
    """
    Lance le screener sur une liste de tickers.
    Retourne les résultats triés par score.
    """
    tickers = tickers or ALL_TICKERS
    top_n   = top_n   or DASHBOARD["top_n"]
    results = []

    # Fetch benchmark (SPY) + VIX regime (once for the whole run)
    benchmark_df = fetch_benchmark("SPY", period="1y")
    vix_data = fetch_vix()
    vix_level = vix_data["vix_level"]
    vix_regime = vix_data["regime"]
    vix_color = {"green": "green", "orange": "yellow", "red": "red", "gray": "dim"}.get(vix_data["color"], "dim")

    vix_display = f"VIX {vix_level} — {vix_regime}" if vix_level else "VIX unavailable"

    console.print(Panel(
        f"[bold cyan]📊 Stock Analyzer[/bold cyan]\n"
        f"Analyse de {len(tickers)} actifs — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"Market regime: [{vix_color}]{vix_display}[/{vix_color}]",
        expand=False
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyse en cours...", total=len(tickers))

        for ticker in tickers:
            progress.update(task, description=f"[cyan]{ticker:<12}[/cyan]")
            try:
                result = analyze_ticker(ticker, vix_regime=vix_regime, benchmark_df=benchmark_df)
                if result:
                    results.append(result)
            except Exception as e:
                pass  # On ignore silencieusement les erreurs individuelles
            progress.advance(task)
            time.sleep(0.1)  # Rate limiting poli

    ranked = rank_stocks(results, max_per_sector=max_per_sector)

    # Afficher le tableau des résultats
    _print_results_table(ranked[:top_n])

    # Sauvegarder les résultats
    output_path = "results_latest.json"
    with open(output_path, "w") as f:
        json.dump(ranked, f, indent=2, default=str)
    console.print(f"\n[dim]💾 Résultats sauvegardés dans {output_path}[/dim]")

    return ranked


def _print_results_table(results: list[dict]):
    """Affiche un tableau Rich des meilleurs résultats."""
    table = Table(
        title=f"🏆 Top {len(results)} Actions",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
    )

    table.add_column("Rank",    style="dim",    width=5,  justify="right")
    table.add_column("Ticker",  style="bold",   width=8)
    table.add_column("Name",                    width=25, no_wrap=True)
    table.add_column("Sector",                  width=18, no_wrap=True)
    table.add_column("Price",   justify="right", width=8)
    table.add_column("Score",   justify="right", width=8)
    table.add_column("Signal",                   width=12)
    table.add_column("Mom 60d", justify="right", width=8)
    table.add_column("vs SPY",  justify="right", width=8)
    table.add_column("RSI",     justify="right", width=6)
    table.add_column("R/R",     justify="right", width=6)

    colors = {
        "FORT ACHAT":  "bright_green",
        "ACHAT":       "green",
        "NEUTRE":      "white",
        "SURVEILLER":  "yellow",
        "PRUDENCE":    "yellow",
        "ÉVITER":      "red",
    }

    for i, r in enumerate(results, 1):
        rec = r.get("recommendation", "?")
        color = colors.get(rec, "white")
        mom60 = r.get("momentum_60d", 0)
        mom_str = f"+{mom60:.1f}%" if mom60 >= 0 else f"{mom60:.1f}%"
        mom_color = "green" if mom60 > 0 else "red"

        excess = r.get("excess_return_60d", 0)
        excess_str = f"+{excess:.1f}%" if excess >= 0 else f"{excess:.1f}%"
        excess_color = "green" if excess > 0 else "red"

        ticker_display = r["ticker"]
        if r.get("earnings_soon"):
            ticker_display += " ⚡"

        table.add_row(
            str(i),
            ticker_display,
            r["name"][:24],
            r.get("sector", "")[:17],
            f"{r['currency'][0] if r['currency'] else '$'}{r['price']:,.2f}",
            f"[{color}]{r['score']:.1f}[/{color}]",
            f"[{color}]{r['emoji']} {rec}[/{color}]",
            f"[{mom_color}]{mom_str}[/{mom_color}]",
            f"[{excess_color}]{excess_str}[/{excess_color}]",
            str(r.get("rsi", "-")),
            f"{r.get('rr_ratio', '-')}:1",
        )

    console.print(table)

    # Show earnings warning if any
    earnings_tickers = [r for r in results if r.get("earnings_soon")]
    if earnings_tickers:
        console.print(f"\n[bold yellow]⚡ Earnings within 7 days:[/bold yellow] "
                      + ", ".join(f"{r['ticker']} ({r['earnings_date']})" for r in earnings_tickers))

    # Top 3 detail
    console.print("\n[bold]💡 Top 3 detailed analysis:[/bold]")
    for r in results[:3]:
        console.print(f"\n[bold cyan]{r['ticker']}[/bold cyan] — {r['name']}")
        for reason in r.get("reasons", []):
            console.print(f"  {reason}")
        if r.get("earnings_soon"):
            console.print(f"  [yellow]⚡ EARNINGS on {r['earnings_date']} — consider waiting[/yellow]")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stock Analyzer — Screener intelligent")
    parser.add_argument("--universe", choices=list(UNIVERSES.keys()) + ["ALL"], default="ALL",
                        help="Univers d'actions à analyser")
    parser.add_argument("--top", type=int, default=15,
                        help="Nombre de résultats à afficher")
    parser.add_argument("--tickers", nargs="+",
                        help="Specific tickers to analyze")
    parser.add_argument("--max-per-sector", type=int, default=0,
                        help="Max stocks per sector in results (0 = no cap)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.universe == "ALL":
        tickers = ALL_TICKERS
    else:
        tickers = UNIVERSES[args.universe]

    run_screener(tickers=tickers, top_n=args.top, max_per_sector=args.max_per_sector)
