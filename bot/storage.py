# bot/storage.py — Snapshot storage for digest diffing.
#
# Local filesystem by default; swap `_backend` to GCS later without touching
# callers. Stores daily snapshots of screener results so the next morning's
# digest can diff against them.

import json
import os
from datetime import date
from pathlib import Path

SNAPSHOT_DIR = Path(os.environ.get("BOTTIBOT_SNAPSHOT_DIR", ".snapshots"))


def _path_for(day: date) -> Path:
    return SNAPSHOT_DIR / f"results_{day.isoformat()}.json"


def save_snapshot(results: list[dict], day: date | None = None) -> Path:
    day = day or date.today()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(day)
    path.write_text(json.dumps(results, indent=2, default=str))
    return path


def load_snapshot(day: date) -> list[dict] | None:
    path = _path_for(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def load_previous_snapshot(before: date | None = None) -> list[dict] | None:
    """Most recent snapshot strictly before `before` (default: today)."""
    before = before or date.today()
    if not SNAPSHOT_DIR.exists():
        return None
    candidates = sorted(SNAPSHOT_DIR.glob("results_*.json"), reverse=True)
    for path in candidates:
        try:
            day_str = path.stem.removeprefix("results_")
            day = date.fromisoformat(day_str)
        except ValueError:
            continue
        if day < before:
            return json.loads(path.read_text())
    return None
