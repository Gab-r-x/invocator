import json
import os
from datetime import datetime, timezone
from pathlib import Path

from invocator.config import Settings
from invocator.models import RepoRef


class CacheCorruptError(RuntimeError):
    def __init__(self, path: Path, line_number: int, original_error: Exception) -> None:
        super().__init__(f"Corrupt JSONL at {path}:{line_number}: {original_error}")
        self.path = path
        self.line_number = line_number
        self.original_error = original_error


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def cache_root(*, settings: Settings) -> Path:
    return settings.cache_dir


def repo_cache_dir(*, settings: Settings, repo: RepoRef) -> Path:
    root = cache_root(settings=settings)
    path = root / f"{repo.owner}__{repo.name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                out.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise CacheCorruptError(path, line_number, exc) from exc
    return out


def append_jsonl(*, path: Path, items: list[dict]) -> int:
    if not items:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item) + "\n")
    return len(items)


def merge_by_id(*, path: Path, items: list[dict], id_field: str) -> tuple[int, int]:
    existing = read_jsonl(path) if path.exists() else []
    merged: dict = {}
    for row in existing:
        merged[row[id_field]] = row

    added = 0
    updated = 0
    for item in items:
        key = item[id_field]
        if key in merged:
            updated += 1
        else:
            added += 1
        merged[key] = item

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for row in merged.values():
            fh.write(json.dumps(row) + "\n")
    os.replace(tmp_path, path)
    return (added, updated)


def _watermark_path(*, settings: Settings, repo: RepoRef) -> Path:
    return repo_cache_dir(settings=settings, repo=repo) / "watermark.json"


def load_watermark(*, settings: Settings, repo: RepoRef) -> dict:
    path = _watermark_path(settings=settings, repo=repo)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_watermark(*, settings: Settings, repo: RepoRef, watermark: dict) -> None:
    path = _watermark_path(settings=settings, repo=repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(watermark, fh, indent=2)
    os.replace(tmp_path, path)


def update_resource_watermark(
    *,
    settings: Settings,
    repo: RepoRef,
    resource: str,
    timestamp_utc: datetime,
) -> None:
    watermark = load_watermark(settings=settings, repo=repo)
    per_resource = watermark.get("per_resource") or {}
    per_resource[resource] = _to_iso_z(timestamp_utc)
    watermark["per_resource"] = per_resource
    watermark["last_run_utc"] = _utc_now_iso()
    save_watermark(settings=settings, repo=repo, watermark=watermark)
