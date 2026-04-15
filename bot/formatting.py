# bot/formatting.py — Telegram Markdown formatter for digests and ticker analyses.

from datetime import datetime


def _escape(text: str) -> str:
    """Escape Telegram MarkdownV2 reserved chars in plain text segments."""
    reserved = r"_*[]()~`>#+-=|{}.!\\"
    return "".join("\\" + c if c in reserved else c for c in str(text))


def _fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


def _row(r: dict) -> str:
    mom = r.get("momentum_60d", 0)
    rs = r.get("excess_return_60d", 0)
    return (
        f"{_escape(r['emoji'])} *{_escape(r['ticker'])}* "
        f"`{r['score']:.1f}` {_escape(r['recommendation'])} "
        f"\\| 60d {_escape(_fmt_pct(mom))} vs SPY {_escape(_fmt_pct(rs))}"
    )


def format_digest_markdown(digest: dict) -> str:
    """Render a digest as Telegram MarkdownV2. Safe to send as-is."""
    today = datetime.now().strftime("%A %d %B %Y")
    lines = [f"📊 *Morning digest* — {_escape(today)}", f"_Universe: {_escape(digest['universe'])}_", ""]

    lines.append(f"*🏆 Top {digest['top_n']}*")
    for r in digest["top"]:
        lines.append(_row(r))
        sl = r.get("stop_loss_pct")
        tp = r.get("take_profit_pct")
        rr = r.get("rr_ratio")
        if sl and tp:
            lines.append(f"  SL `{_escape(str(sl))}%` \\| TP `\\+{_escape(str(tp))}%` \\| R/R `{_escape(str(rr))}:1`")
    lines.append("")

    if digest["entered_buy"]:
        lines.append("*🟢 New BUY signals*")
        for r in digest["entered_buy"]:
            lines.append(f"• *{_escape(r['ticker'])}* — {_escape(r['recommendation'])} `{r['score']:.1f}`")
        lines.append("")

    if digest["dropped_buy"]:
        lines.append("*🔴 Dropped out of BUY*")
        for r in digest["dropped_buy"]:
            prev = r.get("previous_recommendation", "?")
            lines.append(
                f"• *{_escape(r['ticker'])}* — {_escape(prev)} → {_escape(r['recommendation'])} "
                f"`{r['score']:.1f}`"
            )
        lines.append("")

    if digest["score_movers"]:
        lines.append("*📈 Score movers \\(≥5 pts\\)*")
        for r in digest["score_movers"]:
            delta = r["score_delta"]
            arrow = "▲" if delta > 0 else "▼"
            lines.append(
                f"• {arrow} *{_escape(r['ticker'])}* "
                f"`{r['previous_score']:.1f}` → `{r['score']:.1f}` "
                f"\\({_escape(_fmt_pct(delta))}\\)"
            )
        lines.append("")

    if digest["earnings_soon"]:
        lines.append("*⚡ Earnings within 7 days*")
        for r in digest["earnings_soon"]:
            lines.append(f"• *{_escape(r['ticker'])}* — {_escape(r.get('earnings_date', '?'))}")
        lines.append("")

    if not digest["has_previous"]:
        lines.append("_First run — diffs will appear tomorrow\\._")

    lines.append("")
    lines.append("_Not financial advice\\. Always verify before acting\\._")
    return "\n".join(lines)


def format_ticker_analysis(r: dict) -> str:
    """Render a single-ticker analysis for /score command."""
    lines = [
        f"{_escape(r['emoji'])} *{_escape(r['ticker'])}* — {_escape(r['name'][:40])}",
        f"_{_escape(r.get('sector', 'Unknown'))}_",
        "",
        f"Price `${r['price']:,.2f}` \\| Score `{r['score']:.1f}/100`",
        f"Signal *{_escape(r['recommendation'])}*",
        "",
        f"Momentum 60d `{_escape(_fmt_pct(r.get('momentum_60d', 0)))}` "
        f"\\| vs SPY `{_escape(_fmt_pct(r.get('excess_return_60d', 0)))}`",
        f"RSI `{r.get('rsi', '?')}` \\| EMA aligned {'✅' if r.get('ema_aligned') else '❌'}",
        "",
        f"SL `{_escape(str(r.get('stop_loss_pct', '?')))}%` "
        f"\\| TP `\\+{_escape(str(r.get('take_profit_pct', '?')))}%` "
        f"\\| R/R `{_escape(str(r.get('rr_ratio', '?')))}:1`",
    ]
    if r.get("earnings_soon"):
        lines.append("")
        lines.append(f"⚡ *Earnings on {_escape(r.get('earnings_date', '?'))}*")

    reasons = r.get("reasons", [])[:5]
    if reasons:
        lines.append("")
        lines.append("*Analysis*")
        for reason in reasons:
            lines.append(f"• {_escape(reason)}")

    return "\n".join(lines)
