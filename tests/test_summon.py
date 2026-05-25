import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest
from freezegun import freeze_time

from invocator import summon as summon_mod
from invocator.cache import load_watermark, read_jsonl
from invocator.config import Settings
from invocator.gh_client import GhSubprocessError
from invocator.models import RepoRef
from invocator.result import Result
from invocator.summon import summon_all


def _settings(tmp_path: Path, *, exclude_bots: bool = True) -> Settings:
    return Settings(cache_dir=tmp_path, exclude_bots=exclude_bots)


def _repo() -> RepoRef:
    return RepoRef(owner="o", name="n")


def _ok_branch() -> Result[str]:
    return Result[str](success=True, data="main")


def _ndjson(items: list[dict]) -> bytes:
    return ("\n".join(json.dumps(it) for it in items) + ("\n" if items else "")).encode("utf-8")


def _patch_run_gh(
    monkeypatch: pytest.MonkeyPatch, dispatcher: Callable[[list[str]], bytes]
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run_gh(args: list[str], *, paginate: bool = False) -> bytes:
        calls.append(list(args))
        return dispatcher(args)

    monkeypatch.setattr(summon_mod, "run_gh", fake_run_gh)
    monkeypatch.setattr(summon_mod, "get_default_branch", lambda *, repo: _ok_branch())
    return calls


@freeze_time("2026-05-25T12:00:00Z")
def test_summon_all_empty_returns_zero_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_run_gh(monkeypatch, lambda args: b"")
    res = summon_all(settings=_settings(tmp_path), repo=_repo())
    assert res.success is True
    assert res.data is not None
    stats = res.data
    assert (
        stats.pulls_count,
        stats.issues_count,
        stats.commits_count,
        stats.pr_review_comments_count,
        stats.issue_comments_count,
    ) == (0, 0, 0, 0, 0)

    wm = load_watermark(settings=_settings(tmp_path), repo=_repo())
    assert set(wm["per_resource"].keys()) == {
        "pulls",
        "issues",
        "commits",
        "pr_review_comments",
        "issue_comments",
    }


def _pull_raw(
    *,
    pid: int = 1,
    number: int = 1,
    login: str = "alice",
    updated_at: str = "2026-05-20T00:00:00Z",
) -> dict:
    return {
        "id": pid,
        "number": number,
        "title": "T",
        "body": "B",
        "state": "closed",
        "labels": [{"name": "bug"}],
        "user": {"login": login},
        "merged_at": None,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": updated_at,
    }


def _issue_raw(*, iid: int = 100, login: str = "bob", with_pr: bool = False) -> dict:
    out = {
        "id": iid,
        "number": iid,
        "title": "I",
        "body": "B",
        "state": "open",
        "labels": [],
        "user": {"login": login},
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-02T00:00:00Z",
    }
    if with_pr:
        out["pull_request"] = {"url": "x"}
    return out


def _commit_raw(*, sha: str = "abc", message: str = "fix: x", login: str = "alice") -> dict:
    return {
        "sha": sha,
        "commit": {
            "message": message,
            "author": {"date": "2026-05-01T00:00:00Z"},
        },
        "author": {"login": login},
    }


def test_summon_all_populates_pulls_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            return _ndjson([_pull_raw(pid=1, number=1)])
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    res = summon_all(settings=_settings(tmp_path), repo=_repo())
    assert res.success is True
    rows = read_jsonl(tmp_path / "o__n" / "pulls.jsonl")
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["author_login"] == "alice"


def test_summon_filters_bot_authors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            return _ndjson(
                [
                    _pull_raw(pid=1, number=1, login="dependabot[bot]"),
                    _pull_raw(pid=2, number=2, login="alice"),
                ]
            )
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    summon_all(settings=_settings(tmp_path), repo=_repo())
    rows = read_jsonl(tmp_path / "o__n" / "pulls.jsonl")
    assert [r["id"] for r in rows] == [2]


def test_summon_drops_merge_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/commits?" in endpoint:
            return _ndjson(
                [
                    _commit_raw(sha="aaa", message="Merge pull request #1 from x"),
                    _commit_raw(sha="bbb", message="feat: real change"),
                ]
            )
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    summon_all(settings=_settings(tmp_path), repo=_repo())
    rows = read_jsonl(tmp_path / "o__n" / "commits.jsonl")
    assert [r["sha"] for r in rows] == ["bbb"]


def test_summon_issues_endpoint_filters_pull_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/issues?" in endpoint and "/comments" not in endpoint:
            return _ndjson(
                [
                    _issue_raw(iid=10, login="bob", with_pr=False),
                    _issue_raw(iid=11, login="bob", with_pr=True),
                ]
            )
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    summon_all(settings=_settings(tmp_path), repo=_repo())
    rows = read_jsonl(tmp_path / "o__n" / "issues.jsonl")
    assert [r["id"] for r in rows] == [10]


def test_summon_pulls_client_side_since_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    # Pre-seed a watermark for `pulls`.
    from invocator.cache import update_resource_watermark

    update_resource_watermark(
        settings=settings,
        repo=_repo(),
        resource="pulls",
        timestamp_utc=datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc),
    )

    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            return _ndjson(
                [
                    _pull_raw(pid=1, number=1, updated_at="2026-05-10T00:00:00Z"),
                    _pull_raw(pid=2, number=2, updated_at="2026-05-20T00:00:00Z"),
                ]
            )
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    summon_all(settings=settings, repo=_repo())
    rows = read_jsonl(tmp_path / "o__n" / "pulls.jsonl")
    assert [r["id"] for r in rows] == [2]


def test_summon_validation_error_skips_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            good = _pull_raw(pid=1, number=1)
            bad = _pull_raw(pid=2, number=2)
            bad["created_at"] = "not-a-date"
            return _ndjson([good, bad])
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    res = summon_all(settings=_settings(tmp_path), repo=_repo())
    assert res.success is True
    rows = read_jsonl(tmp_path / "o__n" / "pulls.jsonl")
    assert [r["id"] for r in rows] == [1]


def test_summon_fetch_failure_returns_result_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            return _ndjson([_pull_raw(pid=1, number=1)])
        if "/issues?" in endpoint and "/comments" not in endpoint:
            raise GhSubprocessError(
                returncode=1,
                stderr=b"boom",
                args=["gh", "api", endpoint],
            )
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    settings = _settings(tmp_path)
    res = summon_all(settings=settings, repo=_repo())
    assert res.success is False
    assert res.error_code == "SUMMON_FETCH_FAILED"
    # pulls fetched before failure should be persisted
    rows = read_jsonl(tmp_path / "o__n" / "pulls.jsonl")
    assert [r["id"] for r in rows] == [1]
    # issues file should NOT exist (no items, append_jsonl/merge skipped because we raised)
    assert not (tmp_path / "o__n" / "issues.jsonl").exists()


def test_summon_watermark_intermediate_state_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def dispatcher(args: list[str]) -> bytes:
        endpoint = args[1]
        if "/pulls?" in endpoint and "/comments" not in endpoint:
            return _ndjson([_pull_raw(pid=1, number=1)])
        if "/issues?" in endpoint and "/comments" not in endpoint:
            raise GhSubprocessError(returncode=1, stderr=b"boom", args=["gh", "api", endpoint])
        return b""

    _patch_run_gh(monkeypatch, dispatcher)
    settings = _settings(tmp_path)
    summon_all(settings=settings, repo=_repo())
    wm = load_watermark(settings=settings, repo=_repo())
    per_resource = wm.get("per_resource", {})
    assert "pulls" in per_resource
    assert "issues" not in per_resource
