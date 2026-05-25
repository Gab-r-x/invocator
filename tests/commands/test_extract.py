from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from invocator.cli import app
from invocator.models import (
    Category,
    ClassifyStats,
    RepoRef,
    SummonStats,
    SynthesisStats,
)
from invocator.result import Result

runner = CliRunner()


# --------------------------- helpers ----------------------------------------


def _ok_summon() -> Result[SummonStats]:
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    return Result(
        success=True,
        data=SummonStats(
            pulls_count=0,
            issues_count=0,
            commits_count=0,
            pr_review_comments_count=0,
            issue_comments_count=0,
            started_at_utc=now,
            finished_at_utc=now,
        ),
    )


def _ok_classify() -> Result[ClassifyStats]:
    return Result(success=True, data=ClassifyStats())


def _ok_synth() -> Result[SynthesisStats]:
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    return Result(
        success=True,
        data=SynthesisStats(
            total_cost_usd_cents=1234,
            categories_cached=0,
            categories_synthesized=5,
            started_at_utc=now,
            finished_at_utc=now,
        ),
    )


def _ok_dry_synth() -> Result[SynthesisStats]:
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    return Result(
        success=True,
        data=SynthesisStats(
            total_cost_usd_cents=0,
            categories_cached=0,
            categories_synthesized=5,
            started_at_utc=now,
            finished_at_utc=now,
        ),
    )


def _patch_prechecks(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    mocks: dict[str, MagicMock] = {}
    mocks["check_gh_installed"] = MagicMock(return_value=Result(success=True, data=None))
    mocks["check_auth"] = MagicMock(return_value=Result(success=True, data=None))
    mocks["parse_repo"] = MagicMock(
        return_value=Result(success=True, data=RepoRef(owner="owner", name="name"))
    )
    mocks["get_default_branch"] = MagicMock(return_value=Result(success=True, data="main"))
    mocks["load_api_key"] = MagicMock(return_value=Result(success=True, data="sk-ant-test-FAKE"))
    for name, mock in mocks.items():
        monkeypatch.setattr(f"invocator.commands.extract.{name}", mock)
    return mocks


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    summon: Result[SummonStats] | None = None,
    classify: Result[ClassifyStats] | None = None,
    synth: Result[SynthesisStats] | None = None,
    render: Any = None,
) -> dict[str, MagicMock]:
    mocks: dict[str, MagicMock] = {}
    mocks["summon_all"] = MagicMock(return_value=summon if summon is not None else _ok_summon())
    mocks["classify"] = MagicMock(return_value=classify if classify is not None else _ok_classify())
    mocks["synthesize_all"] = MagicMock(return_value=synth if synth is not None else _ok_synth())
    mocks["render_cost_preview"] = MagicMock(return_value=render)
    for name, mock in mocks.items():
        monkeypatch.setattr(f"invocator.commands.extract.{name}", mock)
    return mocks


def _patch_confirm(monkeypatch: pytest.MonkeyPatch, *, return_value: bool = True) -> MagicMock:
    confirm = MagicMock(return_value=return_value)
    monkeypatch.setattr("invocator.commands.extract.typer.confirm", confirm)
    return confirm


# --------------------------- pipeline happy paths ---------------------------


def test_happy_dry_run_writes_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "learnings"
    cache = tmp_path / "cache"
    _patch_prechecks(monkeypatch)

    def fake_synth(**kwargs: Any) -> Result[SynthesisStats]:
        out_dir = kwargs["settings"].out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for cat in Category:
            (out_dir / f"{cat.value}.md").write_text("- item one\n- item two\n", encoding="utf-8")
        (out_dir / "INDEX.md").write_text("# index\n", encoding="utf-8")
        return _ok_dry_synth()

    pipeline = _patch_pipeline(monkeypatch)
    pipeline["synthesize_all"].side_effect = fake_synth
    pipeline["synthesize_all"].return_value = None  # use side_effect
    _patch_confirm(monkeypatch, return_value=True)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(out),
            "--cache-dir",
            str(cache),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    for cat in Category:
        assert (out / f"{cat.value}.md").exists()
    assert (out / "INDEX.md").exists()
    assert "Done" in result.output


def test_happy_non_dry_run_calls_synth_with_dry_run_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch, return_value=True)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pipeline["synthesize_all"].call_count == 1
    assert pipeline["synthesize_all"].call_args.kwargs["dry_run"] is False


def test_yes_skips_confirm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    _patch_pipeline(monkeypatch)
    confirm = _patch_confirm(monkeypatch, return_value=True)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert confirm.call_count == 0


def test_explicit_confirm_yes_proceeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    confirm = _patch_confirm(monkeypatch, return_value=True)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert confirm.call_count == 1
    assert pipeline["summon_all"].call_count == 1


# --------------------------- pre-check failures -----------------------------


def test_gh_not_installed_exit_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mocks = _patch_prechecks(monkeypatch)
    mocks["check_gh_installed"].return_value = Result(
        success=False, error_code="GH_NOT_INSTALLED", error_message="gh CLI not found"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 2
    assert pipeline["summon_all"].call_count == 0


def test_check_auth_failed_exit_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mocks = _patch_prechecks(monkeypatch)
    mocks["check_auth"].return_value = Result(
        success=False, error_code="GH_NOT_AUTHENTICATED", error_message="not auth'd"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        ["extract", "wisdom", "--repo", "owner/name", "--dry-run", "--yes"],
    )

    assert result.exit_code == 2
    assert pipeline["summon_all"].call_count == 0


def test_parse_repo_invalid_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_prechecks(monkeypatch)
    mocks["parse_repo"].return_value = Result(
        success=False, error_code="INVALID_REPO", error_message="bad repo"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        ["extract", "wisdom", "--repo", "garbage", "--dry-run", "--yes"],
    )

    assert result.exit_code == 2
    assert pipeline["summon_all"].call_count == 0


def test_repo_not_found_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_prechecks(monkeypatch)
    mocks["get_default_branch"].return_value = Result(
        success=False, error_code="REPO_NOT_FOUND", error_message="no repo"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        ["extract", "wisdom", "--repo", "owner/name", "--dry-run", "--yes"],
    )

    assert result.exit_code == 2
    assert pipeline["summon_all"].call_count == 0


def test_no_api_key_without_dry_run_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_prechecks(monkeypatch)
    mocks["load_api_key"].return_value = Result(
        success=False, error_code="NO_API_KEY", error_message="no key"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        ["extract", "wisdom", "--repo", "owner/name", "--yes"],
    )

    assert result.exit_code == 2
    assert pipeline["summon_all"].call_count == 0
    combined = result.output + (result.stderr if result.stderr_bytes else "")
    assert "invocator forge key" in combined


def test_dry_run_skips_api_key_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mocks = _patch_prechecks(monkeypatch)
    # Even though load_api_key would fail, --dry-run skips it entirely.
    mocks["load_api_key"].return_value = Result(
        success=False, error_code="NO_API_KEY", error_message="no key"
    )
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pipeline["summon_all"].call_count == 1


# --------------------------- user abort -------------------------------------


def test_user_abort_via_confirm_exit_0(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch, return_value=False)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pipeline["summon_all"].call_count == 0
    assert "Aborted" in result.output


# --------------------------- mid-run failures -------------------------------


def test_summon_failure_exit_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(
        monkeypatch,
        summon=Result(success=False, error_code="SUMMON_FETCH_FAILED", error_message="rate limit"),
    )
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 1
    assert pipeline["classify"].call_count == 0


def test_classify_failure_exit_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(
        monkeypatch,
        classify=Result(success=False, error_code="CLASSIFY_FAILED", error_message="oops"),
    )
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 1
    assert pipeline["synthesize_all"].call_count == 0


def test_synthesize_failure_exit_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    _patch_pipeline(
        monkeypatch,
        synth=Result(success=False, error_code="ANTHROPIC_API_ERROR", error_message="api down"),
    )
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 1


# --------------------------- flag plumbing ----------------------------------


def test_force_refetch_removes_watermark(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    cache_dir = tmp_path / "cache"
    repo_cache = cache_dir / "owner__name"
    repo_cache.mkdir(parents=True)
    watermark_path = repo_cache / "watermark.json"
    watermark_path.write_text("{}", encoding="utf-8")
    assert watermark_path.exists()

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(cache_dir),
            "--dry-run",
            "--yes",
            "--force-refetch",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not watermark_path.exists()


def test_since_parsed_to_utc_passed_to_summon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
            "--since",
            "2024-01-01",
        ],
    )

    assert result.exit_code == 0, result.output
    since_arg = pipeline["summon_all"].call_args.kwargs["since"]
    assert isinstance(since_arg, datetime)
    assert since_arg == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_top_k_propagates_to_classify(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
            "--top-k",
            "100",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pipeline["classify"].call_args.kwargs["top_k"] == 100


def test_model_propagates_to_synth_and_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
            "--model",
            "claude-opus-4-7",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pipeline["synthesize_all"].call_args.kwargs["model"] == "claude-opus-4-7"
    assert pipeline["render_cost_preview"].call_args.kwargs["model"] == "claude-opus-4-7"


def test_cache_dir_flag_reaches_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    cache_dir = tmp_path / "custom-cache"

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(cache_dir),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    for step in ("summon_all", "classify", "synthesize_all"):
        settings = pipeline[step].call_args.kwargs["settings"]
        assert settings.cache_dir == cache_dir


def test_out_flag_reaches_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    out_dir = tmp_path / "custom-out"

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(out_dir),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    settings = pipeline["synthesize_all"].call_args.kwargs["settings"]
    assert settings.out_dir == out_dir


# --------------------------- settings construction --------------------------


def test_settings_built_from_cli_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    pipeline = _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
            "--top-k",
            "77",
            "--model",
            "claude-opus-4-7",
        ],
    )

    assert result.exit_code == 0, result.output
    settings = pipeline["summon_all"].call_args.kwargs["settings"]
    assert settings.top_k_per_category == 77
    assert settings.model == "claude-opus-4-7"


# --------------------------- final summary ----------------------------------


def test_dry_run_summary_lists_five_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_prechecks(monkeypatch)
    out = tmp_path / "out"

    def fake_synth(**kwargs: Any) -> Result[SynthesisStats]:
        out_dir = kwargs["settings"].out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for cat in Category:
            (out_dir / f"{cat.value}.md").write_text("- one\n", encoding="utf-8")
        (out_dir / "INDEX.md").write_text("# index\n", encoding="utf-8")
        return _ok_dry_synth()

    pipeline = _patch_pipeline(monkeypatch)
    pipeline["synthesize_all"].side_effect = fake_synth
    pipeline["synthesize_all"].return_value = None
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(out),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    for cat in Category:
        assert f"{cat.value}.md" in result.output
    assert "INDEX.md" in result.output


def test_non_dry_run_summary_includes_dollar_cost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_prechecks(monkeypatch)
    _patch_pipeline(monkeypatch)
    _patch_confirm(monkeypatch)

    result = runner.invoke(
        app,
        [
            "extract",
            "wisdom",
            "--repo",
            "owner/name",
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "$" in result.output
