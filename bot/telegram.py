# bot/telegram.py — One-way Telegram sender for the morning digest.
#
# Uses the Telegram Bot HTTP API directly (no framework needed for push-only).
# Requires env vars:
#   TELEGRAM_BOT_TOKEN  — from @BotFather
#   TELEGRAM_CHAT_ID    — your personal chat ID (use @userinfobot to find it)

from __future__ import annotations

import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4000  # Telegram hard limit is 4096; leave headroom


class TelegramError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise TelegramError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. "
            "Create a bot via @BotFather and find your chat ID via @userinfobot."
        )
    return token, chat_id


def _chunk(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split by blank-line boundary first, then by line, to stay under Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks, buf = [], ""
    for block in text.split("\n\n"):
        piece = (buf + "\n\n" + block) if buf else block
        if len(piece) <= limit:
            buf = piece
        else:
            if buf:
                chunks.append(buf)
            if len(block) <= limit:
                buf = block
            else:
                for line in block.split("\n"):
                    candidate = (buf + "\n" + line) if buf else line
                    if len(candidate) <= limit:
                        buf = candidate
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = line
    if buf:
        chunks.append(buf)
    return chunks


def send_message(text: str, parse_mode: str = "MarkdownV2") -> None:
    token, chat_id = _credentials()
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    for chunk in _chunk(text):
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if not resp.ok:
            raise TelegramError(f"Telegram API error {resp.status_code}: {resp.text}")


def send_digest(universe: str = "US_LARGE", top_n: int = 5, concurrency: int = 5) -> None:
    from bot.digest import generate_digest
    from bot.formatting import format_digest_markdown

    digest = generate_digest(universe=universe, top_n=top_n, concurrency=concurrency)
    send_message(format_digest_markdown(digest))


if __name__ == "__main__":
    import argparse
    from config import UNIVERSES

    parser = argparse.ArgumentParser(description="Send morning digest to Telegram")
    parser.add_argument("--universe", default="US_LARGE", choices=list(UNIVERSES.keys()))
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--test", action="store_true", help="Send a test ping and exit")
    args = parser.parse_args()

    if args.test:
        send_message("✅ *bottibot* connected\\.")
        print("Test message sent.")
    else:
        send_digest(universe=args.universe, top_n=args.top, concurrency=args.concurrency)
        print("Digest sent.")
