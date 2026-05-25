import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from invocator import cache as cache_mod
from invocator.cache import (
    CacheCorruptError,
    append_jsonl,
    load_watermark,
    merge_by_id,
    read_jsonl,
    save_watermark,
    update_resource_watermark,
)
from invocator.config import Settings
from invocator.models import RepoRef


def _settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path)


def _repo() -> RepoRef:
    return RepoRef(owner="o", name="n")


def test_read_jsonl_missing_returns_empty(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "absent.jsonl") == []


def test_append_jsonl_writes_lines(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    n = append_jsonl(path=path, items=[{"id": 1}, {"id": 2}])
    assert n == 2
    assert read_jsonl(path) == [{"id": 1}, {"id": 2}]


def test_append_jsonl_empty_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    n = append_jsonl(path=path, items=[])
    assert n == 0
    assert not path.exists()


def test_merge_by_id_first_call_all_added(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    added, updated = merge_by_id(
        path=path, items=[{"id": 1, "x": "a"}, {"id": 2, "x": "b"}], id_field="id"
    )
    assert (added, updated) == (2, 0)
    assert read_jsonl(path) == [{"id": 1, "x": "a"}, {"id": 2, "x": "b"}]


def test_merge_by_id_overlapping_updates(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    merge_by_id(path=path, items=[{"id": 1, "x": "a"}, {"id": 2, "x": "b"}], id_field="id")
    added, updated = merge_by_id(
        path=path,
        items=[{"id": 2, "x": "B"}, {"id": 3, "x": "c"}],
        id_field="id",
    )
    assert (added, updated) == (1, 1)
    rows = read_jsonl(path)
    by_id = {r["id"]: r["x"] for r in rows}
    assert by_id == {1: "a", 2: "B", 3: "c"}


def test_merge_by_id_preserves_insertion_order(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    merge_by_id(
        path=path,
        items=[{"id": 10, "v": 1}, {"id": 20, "v": 2}, {"id": 30, "v": 3}],
        id_field="id",
    )
    merge_by_id(path=path, items=[{"id": 20, "v": 22}], id_field="id")
    rows = read_jsonl(path)
    assert [r["id"] for r in rows] == [10, 20, 30]
    assert rows[1]["v"] == 22


def test_read_jsonl_corrupt_line_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": 1}\nnot-json\n', encoding="utf-8")
    with pytest.raises(CacheCorruptError) as excinfo:
        read_jsonl(path)
    assert excinfo.value.path == path
    assert excinfo.value.line_number == 2


def test_load_watermark_missing_returns_empty(tmp_path: Path) -> None:
    assert load_watermark(settings=_settings(tmp_path), repo=_repo()) == {}


def test_save_and_load_watermark_round_trip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    payload = {"per_resource": {"pulls": "2026-05-25T12:00:00Z"}, "last_run_utc": "x"}
    save_watermark(settings=settings, repo=repo, watermark=payload)
    assert load_watermark(settings=settings, repo=repo) == payload


@freeze_time("2026-05-25T12:00:00Z")
def test_update_resource_watermark_sets_and_preserves(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    ts1 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 5, 2, 0, 0, 0, tzinfo=timezone.utc)
    update_resource_watermark(settings=settings, repo=repo, resource="pulls", timestamp_utc=ts1)
    update_resource_watermark(settings=settings, repo=repo, resource="issues", timestamp_utc=ts2)
    wm = load_watermark(settings=settings, repo=repo)
    assert wm["per_resource"]["pulls"] == "2026-05-01T00:00:00Z"
    assert wm["per_resource"]["issues"] == "2026-05-02T00:00:00Z"
    assert wm["last_run_utc"] == "2026-05-25T12:00:00Z"


def test_merge_by_id_uses_atomic_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "p.jsonl"
    captured: dict = {}
    real_replace = os.replace

    def fake_replace(src, dst) -> None:
        captured["src"] = str(src)
        captured["dst"] = str(dst)
        real_replace(src, dst)

    monkeypatch.setattr(cache_mod.os, "replace", fake_replace)
    merge_by_id(path=path, items=[{"id": 1}], id_field="id")
    assert captured["src"].endswith(".jsonl.tmp")
    assert captured["dst"] == str(path)


def test_watermark_iso_z_suffix(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    ts = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    update_resource_watermark(settings=settings, repo=repo, resource="commits", timestamp_utc=ts)
    raw = (tmp_path / "o__n" / "watermark.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["per_resource"]["commits"].endswith("Z")
    assert "+00:00" not in data["per_resource"]["commits"]
