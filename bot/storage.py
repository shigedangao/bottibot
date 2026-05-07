# bot/storage.py — Snapshot + cache storage with pluggable backend.
#
# Backend selected via env var BOTTIBOT_STORAGE_BACKEND:
#   "local" (default)  — local filesystem, suitable for dev and Compute Engine
#   "gcs"              — Google Cloud Storage, suitable for Cloud Run (ephemeral fs)
#
# When backend=gcs, set BOTTIBOT_GCS_BUCKET to the bucket name.
# Optional BOTTIBOT_GCS_PREFIX to namespace within the bucket (default "bottibot").

import json
import os
from datetime import date
from pathlib import Path

BACKEND = os.environ.get("BOTTIBOT_STORAGE_BACKEND", "local").lower()
SNAPSHOT_DIR = Path(os.environ.get("BOTTIBOT_SNAPSHOT_DIR", ".snapshots"))
LATEST_PATH = Path(os.environ.get("BOTTIBOT_LATEST_PATH", "results_latest.json"))

GCS_BUCKET = os.environ.get("BOTTIBOT_GCS_BUCKET")
GCS_PREFIX = os.environ.get("BOTTIBOT_GCS_PREFIX", "bottibot")


# ── Local backend ────────────────────────────────────────────────────────────

def _local_snapshot_path(day: date) -> Path:
    return SNAPSHOT_DIR / f"results_{day.isoformat()}.json"


def _local_save_snapshot(results: list[dict], day: date) -> str:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _local_snapshot_path(day)
    path.write_text(json.dumps(results, indent=2, default=str))
    return str(path)


def _local_load_snapshot(day: date) -> list[dict] | None:
    path = _local_snapshot_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _local_load_previous_snapshot(before: date) -> list[dict] | None:
    if not SNAPSHOT_DIR.exists():
        return None
    candidates = sorted(SNAPSHOT_DIR.glob("results_*.json"), reverse=True)
    for path in candidates:
        try:
            day = date.fromisoformat(path.stem.removeprefix("results_"))
        except ValueError:
            continue
        if day < before:
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return None
    return None


def _local_load_all_snapshots() -> list[tuple[date, list[dict]]]:
    if not SNAPSHOT_DIR.exists():
        return []
    out: list[tuple[date, list[dict]]] = []
    for path in sorted(SNAPSHOT_DIR.glob("results_*.json")):
        try:
            day = date.fromisoformat(path.stem.removeprefix("results_"))
            results = json.loads(path.read_text())
            out.append((day, results))
        except (ValueError, json.JSONDecodeError, OSError):
            continue
    return out


def _local_save_latest(results: list[dict]) -> str:
    parent = LATEST_PATH.parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(results, indent=2, default=str))
    return str(LATEST_PATH)


def _local_load_latest() -> list[dict] | None:
    if not LATEST_PATH.exists():
        return None
    try:
        return json.loads(LATEST_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ── GCS backend ──────────────────────────────────────────────────────────────

def _gcs_bucket():
    if not GCS_BUCKET:
        raise RuntimeError("BOTTIBOT_GCS_BUCKET is not set but BOTTIBOT_STORAGE_BACKEND=gcs")
    from google.cloud import storage  # imported lazily so local dev doesn't need the dep
    return storage.Client().bucket(GCS_BUCKET)


def _gcs_blob(name: str):
    return _gcs_bucket().blob(f"{GCS_PREFIX}/{name}")


def _gcs_save_snapshot(results: list[dict], day: date) -> str:
    blob = _gcs_blob(f"snapshots/results_{day.isoformat()}.json")
    blob.upload_from_string(
        json.dumps(results, indent=2, default=str),
        content_type="application/json",
    )
    return f"gs://{GCS_BUCKET}/{blob.name}"


def _gcs_load_snapshot(day: date) -> list[dict] | None:
    blob = _gcs_blob(f"snapshots/results_{day.isoformat()}.json")
    if not blob.exists():
        return None
    try:
        return json.loads(blob.download_as_text())
    except (json.JSONDecodeError, Exception):
        return None


def _gcs_load_previous_snapshot(before: date) -> list[dict] | None:
    bucket = _gcs_bucket()
    prefix = f"{GCS_PREFIX}/snapshots/results_"
    blobs = list(bucket.list_blobs(prefix=prefix))
    candidates = []
    for b in blobs:
        stem = b.name.split("/")[-1].removeprefix("results_").removesuffix(".json")
        try:
            day = date.fromisoformat(stem)
        except ValueError:
            continue
        if day < before:
            candidates.append((day, b))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, latest_blob = candidates[0]
    try:
        return json.loads(latest_blob.download_as_text())
    except (json.JSONDecodeError, Exception):
        return None


def _gcs_load_all_snapshots() -> list[tuple[date, list[dict]]]:
    bucket = _gcs_bucket()
    prefix = f"{GCS_PREFIX}/snapshots/results_"
    blobs = list(bucket.list_blobs(prefix=prefix))
    out: list[tuple[date, list[dict]]] = []
    for b in blobs:
        stem = b.name.split("/")[-1].removeprefix("results_").removesuffix(".json")
        try:
            day = date.fromisoformat(stem)
            results = json.loads(b.download_as_text())
            out.append((day, results))
        except (ValueError, json.JSONDecodeError, Exception):
            continue
    out.sort(key=lambda x: x[0])
    return out


def _gcs_save_latest(results: list[dict]) -> str:
    blob = _gcs_blob("results_latest.json")
    blob.upload_from_string(
        json.dumps(results, indent=2, default=str),
        content_type="application/json",
    )
    return f"gs://{GCS_BUCKET}/{blob.name}"


def _gcs_load_latest() -> list[dict] | None:
    blob = _gcs_blob("results_latest.json")
    if not blob.exists():
        return None
    try:
        return json.loads(blob.download_as_text())
    except (json.JSONDecodeError, Exception):
        return None


# ── Public API ───────────────────────────────────────────────────────────────

def save_snapshot(results: list[dict], day: date | None = None) -> str:
    day = day or date.today()
    if BACKEND == "gcs":
        return _gcs_save_snapshot(results, day)
    return _local_save_snapshot(results, day)


def load_snapshot(day: date) -> list[dict] | None:
    if BACKEND == "gcs":
        return _gcs_load_snapshot(day)
    return _local_load_snapshot(day)


def load_previous_snapshot(before: date | None = None) -> list[dict] | None:
    """Most recent snapshot strictly before `before` (default: today)."""
    before = before or date.today()
    if BACKEND == "gcs":
        return _gcs_load_previous_snapshot(before)
    return _local_load_previous_snapshot(before)


def save_latest(results: list[dict]) -> str:
    """Persist the latest screener output for the dashboard cache."""
    if BACKEND == "gcs":
        return _gcs_save_latest(results)
    return _local_save_latest(results)


def load_latest() -> list[dict] | None:
    """Load the cached latest screener output (returns None if missing)."""
    if BACKEND == "gcs":
        return _gcs_load_latest()
    return _local_load_latest()


def load_all_snapshots() -> list[tuple[date, list[dict]]]:
    """Return every saved snapshot as (date, results) sorted ascending by date."""
    if BACKEND == "gcs":
        return _gcs_load_all_snapshots()
    return _local_load_all_snapshots()


def score_history_for_ticker(ticker: str) -> list[dict]:
    """
    Return chronological score history for a single ticker pulled from the
    daily snapshots. Each entry: {date, score, recommendation, emoji}.
    Days where the ticker was not screened are simply absent.
    """
    history: list[dict] = []
    for day, results in load_all_snapshots():
        for r in results:
            if r.get("ticker") == ticker:
                history.append({
                    "date":           day.isoformat(),
                    "score":          r.get("score"),
                    "recommendation": r.get("recommendation"),
                    "emoji":          r.get("emoji"),
                })
                break
    return history
