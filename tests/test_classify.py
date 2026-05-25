import json
from pathlib import Path

import pytest

from invocator import classify as classify_mod
from invocator.classify import classify
from invocator.config import Settings
from invocator.models import Category, RepoRef


def _settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path)


def _repo() -> RepoRef:
    return RepoRef(owner="o", name="n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _repo_dir(tmp_path: Path) -> Path:
    return tmp_path / "o__n"


def test_classify_populated_cache_writes_all_five_files(tmp_path: Path) -> None:
    repo_dir = _repo_dir(tmp_path)
    _write_jsonl(
        repo_dir / "pulls.jsonl",
        [
            {
                "id": 1,
                "number": 1,
                "title": "fix: handle race",
                "body": "Always validate input.",
                "labels": ["bug"],
            },
            {
                "id": 2,
                "number": 2,
                "title": "ADR-001: choose Postgres",
                "body": "## Context\nc\n\n## Decision\nd",
                "labels": ["architecture"],
            },
            {
                "id": 3,
                "number": 3,
                "title": "refactor: extract helper",
                "body": None,
                "labels": ["refactor"],
            },
        ],
    )
    _write_jsonl(
        repo_dir / "issues.jsonl",
        [
            {
                "id": 10,
                "number": 10,
                "title": "thing about `fooBar`",
                "body": "never do that",
                "labels": ["glossary"],
            }
        ],
    )
    _write_jsonl(
        repo_dir / "commits.jsonl",
        [{"sha": "abc1234567890", "message": "fix: another bug"}],
    )

    result = classify(settings=_settings(tmp_path), repo=_repo())
    assert result.success
    assert result.data is not None
    stats = result.data
    classified_dir = repo_dir / "classified"
    for cat in Category:
        assert (classified_dir / f"{cat.value}.jsonl").exists()
    assert stats.rules_count > 0
    assert stats.prevencoes_count > 0
    assert stats.patterns_count > 0
    assert stats.decisions_count > 0


def test_classify_dedupes_identical_conventional_commits(tmp_path: Path) -> None:
    repo_dir = _repo_dir(tmp_path)
    _write_jsonl(
        repo_dir / "pulls.jsonl",
        [
            {"id": 1, "number": 1, "title": "fix: race", "body": None, "labels": []},
            {"id": 2, "number": 2, "title": "fix: race", "body": None, "labels": []},
        ],
    )
    result = classify(settings=_settings(tmp_path), repo=_repo())
    assert result.success
    assert result.data is not None
    prev_path = repo_dir / "classified" / "prevencoes.jsonl"
    lines = [ln for ln in prev_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert result.data.dropped_dupes >= 1


def test_classify_top_k_cap_drops_overflow(tmp_path: Path) -> None:
    repo_dir = _repo_dir(tmp_path)
    pulls = [
        {
            "id": i,
            "number": i,
            "title": f"unique convention pr title #{i}",
            "body": None,
            "labels": ["convention"],
        }
        for i in range(1, 601)
    ]
    _write_jsonl(repo_dir / "pulls.jsonl", pulls)
    result = classify(settings=_settings(tmp_path), repo=_repo(), top_k=100)
    assert result.success
    assert result.data is not None
    rules_path = repo_dir / "classified" / "rules.jsonl"
    lines = [ln for ln in rules_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 100
    assert result.data.dropped_top_k == 500


def test_classify_glossary_threshold_includes_backticked_term(tmp_path: Path) -> None:
    repo_dir = _repo_dir(tmp_path)
    _write_jsonl(
        repo_dir / "pulls.jsonl",
        [
            {"id": 1, "number": 1, "title": "use `fooBar` here", "body": None, "labels": []},
            {"id": 2, "number": 2, "title": "also `fooBar` again", "body": None, "labels": []},
        ],
    )
    _write_jsonl(
        repo_dir / "issues.jsonl",
        [
            {"id": 11, "number": 11, "title": "more `fooBar` work", "body": None, "labels": []},
            {"id": 12, "number": 12, "title": "still `fooBar` pending", "body": None, "labels": []},
        ],
    )
    result = classify(settings=_settings(tmp_path), repo=_repo())
    assert result.success
    gloss_path = repo_dir / "classified" / "glossary.jsonl"
    rows = [json.loads(ln) for ln in gloss_path.read_text().splitlines() if ln.strip()]
    foobar_rows = [r for r in rows if r["snippet"] == "fooBar"]
    assert len(foobar_rows) == 1
    assert foobar_rows[0]["weight"] >= 3


def test_classify_is_idempotent(tmp_path: Path) -> None:
    repo_dir = _repo_dir(tmp_path)
    _write_jsonl(
        repo_dir / "pulls.jsonl",
        [
            {
                "id": 1,
                "number": 1,
                "title": "fix: bug",
                "body": "Always validate input.",
                "labels": ["bug"],
            }
        ],
    )
    classify(settings=_settings(tmp_path), repo=_repo())
    classified_dir = repo_dir / "classified"
    first_snapshot = {
        cat.value: (classified_dir / f"{cat.value}.jsonl").read_bytes() for cat in Category
    }
    classify(settings=_settings(tmp_path), repo=_repo())
    second_snapshot = {
        cat.value: (classified_dir / f"{cat.value}.jsonl").read_bytes() for cat in Category
    }
    assert first_snapshot == second_snapshot


def test_classify_atomic_write_uses_os_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = _repo_dir(tmp_path)
    _write_jsonl(
        repo_dir / "pulls.jsonl",
        [{"id": 1, "number": 1, "title": "fix: x", "body": None, "labels": []}],
    )

    calls: list[tuple[str, str]] = []
    real_replace = classify_mod.os.replace

    def spy_replace(src, dst):  # type: ignore[no-untyped-def]
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(classify_mod.os, "replace", spy_replace)
    result = classify(settings=_settings(tmp_path), repo=_repo())
    assert result.success
    classified_calls = [c for c in calls if "classified" in c[1]]
    assert len(classified_calls) == 5
    for src, dst in classified_calls:
        assert src.endswith(".tmp")
        assert dst.endswith(".jsonl")
