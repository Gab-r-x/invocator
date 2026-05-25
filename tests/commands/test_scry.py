import json

import pytest
from typer.testing import CliRunner

from invocator.cli import app
from invocator.commands.scry import estimate_cost, probe_endpoint
from invocator.gh_client import GhSubprocessError
from invocator.models import RepoRef
from invocator.result import Result

runner = CliRunner()


def _ok_branch(*, repo: RepoRef) -> Result[str]:  # noqa: ARG001
    return Result[str](success=True, data="main")


def _ok_parse(*, value: str) -> Result[RepoRef]:
    owner, _, name = value.partition("/")
    return Result[RepoRef](success=True, data=RepoRef(owner=owner, name=name))


def _ok_check() -> Result[None]:
    return Result[None](success=True, data=None)


def _patch_prechecks_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("invocator.commands.scry.check_gh_installed", _ok_check)
    monkeypatch.setattr("invocator.commands.scry.check_auth", _ok_check)
    monkeypatch.setattr("invocator.commands.scry.parse_repo", _ok_parse)
    monkeypatch.setattr("invocator.commands.scry.get_default_branch", _ok_branch)


def _link_header_response(*, last_page: int, body_items: int = 1) -> bytes:
    body_list = [{"id": i} for i in range(body_items)]
    body = json.dumps(body_list)
    headers = (
        "HTTP/2.0 200 OK\r\n"
        f'Link: <https://api.github.com/x?per_page=1&page={last_page}>; rel="last"\r\n'
        "Other: x\r\n"
        "\r\n"
    )
    return headers.encode("utf-8") + body.encode("utf-8")


def _no_link_response(*, body_items: int) -> bytes:
    body = json.dumps([{"id": i} for i in range(body_items)])
    headers = "HTTP/2.0 200 OK\r\nOther: x\r\n\r\n"
    return headers.encode("utf-8") + body.encode("utf-8")


def test_scry_cost_happy_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prechecks_ok(monkeypatch)

    def fake_run_gh(args: list[str], **kw: object) -> bytes:
        return _link_header_response(last_page=3)

    monkeypatch.setattr("invocator.commands.scry.run_gh", fake_run_gh)

    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "estimated_tokens" in payload
    assert "estimated_cost_usd_cents" in payload
    per_resource = payload["per_resource"]
    assert set(per_resource.keys()) == {
        "pulls",
        "issues",
        "pulls_comments",
        "issues_comments",
        "commits",
    }


def test_scry_cost_rich_table_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prechecks_ok(monkeypatch)
    monkeypatch.setattr(
        "invocator.commands.scry.run_gh",
        lambda args, **kw: _link_header_response(last_page=2),
    )

    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name"])
    assert result.exit_code == 0
    assert "pulls" in result.stdout
    assert "issues" in result.stdout
    assert "Estimated tokens" in result.stdout
    assert "Cost" in result.stdout


def test_scry_cost_opus_5x_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = {
        "pulls": 100,
        "issues": 100,
        "pulls_comments": 100,
        "issues_comments": 100,
        "commits": 100,
    }
    sonnet = estimate_cost(item_counts=counts, model="claude-sonnet-4-6")
    opus = estimate_cost(item_counts=counts, model="claude-opus-4-7")
    assert opus.estimated_cost_usd_cents == 5 * sonnet.estimated_cost_usd_cents


def test_scry_cost_one_endpoint_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prechecks_ok(monkeypatch)

    def fake_run_gh(args: list[str], **kw: object) -> bytes:
        # args looks like ["api", "-i", "repos/owner/name/<resource>?...&per_page=1"]
        endpoint = args[2]
        if "issues_comments" in endpoint or "issues/comments" in endpoint:
            exc = GhSubprocessError(
                returncode=1,
                stderr=b"gh: Not Found (HTTP 404)",
                args=args,
            )
            raise exc
        return _link_header_response(last_page=2)

    monkeypatch.setattr("invocator.commands.scry.run_gh", fake_run_gh)

    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["per_resource"]["issues_comments"] == 0
    assert payload["estimated_tokens"] > 0


def test_scry_cost_one_endpoint_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prechecks_ok(monkeypatch)

    def fake_run_gh(args: list[str], **kw: object) -> bytes:
        endpoint = args[2]
        if "commits" in endpoint:
            raise GhSubprocessError(
                returncode=1,
                stderr=b"gh: some other failure",
                args=args,
            )
        return _link_header_response(last_page=2)

    monkeypatch.setattr("invocator.commands.scry.run_gh", fake_run_gh)

    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name"])
    assert result.exit_code == 0
    # Failed resource should be rendered as dash in the table.
    assert "—" in result.stdout
    # Also: stderr should contain a flag for that resource.
    assert "commits" in (result.stderr or "") + result.stdout


def test_probe_endpoint_link_last_page() -> None:
    raw = _link_header_response(last_page=7)
    # Patch run_gh module-level for this unit call.
    import invocator.commands.scry as scry_mod

    saved = scry_mod.run_gh
    scry_mod.run_gh = lambda args, **kw: raw  # type: ignore[assignment]
    try:
        result = probe_endpoint(endpoint="repos/x/y/pulls?state=all")
    finally:
        scry_mod.run_gh = saved  # type: ignore[assignment]
    assert result.success is True
    # probe uses per_page=1 → last-page number IS the item count
    assert result.data == 7


def test_probe_endpoint_no_link_falls_back_to_body_length() -> None:
    raw = _no_link_response(body_items=12)
    import invocator.commands.scry as scry_mod

    saved = scry_mod.run_gh
    scry_mod.run_gh = lambda args, **kw: raw  # type: ignore[assignment]
    try:
        result = probe_endpoint(endpoint="repos/x/y/pulls?state=all")
    finally:
        scry_mod.run_gh = saved  # type: ignore[assignment]
    assert result.success is True
    assert result.data == 12


def test_scry_cost_gh_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "invocator.commands.scry.check_gh_installed",
        lambda: Result[None](
            success=False,
            error_code="GH_NOT_INSTALLED",
            error_message="gh CLI not found",
        ),
    )
    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name"])
    assert result.exit_code == 2
    combined = result.stdout + (result.stderr or "")
    assert "gh CLI not found" in combined
    assert "Traceback" not in combined


def test_scry_cost_gh_not_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("invocator.commands.scry.check_gh_installed", _ok_check)
    monkeypatch.setattr(
        "invocator.commands.scry.check_auth",
        lambda: Result[None](
            success=False,
            error_code="GH_NOT_AUTHENTICATED",
            error_message="gh not authenticated",
        ),
    )
    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name"])
    assert result.exit_code == 2


def test_scry_cost_invalid_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("invocator.commands.scry.check_gh_installed", _ok_check)
    monkeypatch.setattr("invocator.commands.scry.check_auth", _ok_check)
    monkeypatch.setattr(
        "invocator.commands.scry.parse_repo",
        lambda value: Result[RepoRef](
            success=False,
            error_code="INVALID_REPO",
            error_message="Could not parse repo from: garbage",
        ),
    )
    result = runner.invoke(app, ["scry", "cost", "--repo", "garbage"])
    assert result.exit_code == 2


def test_scry_cost_repo_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("invocator.commands.scry.check_gh_installed", _ok_check)
    monkeypatch.setattr("invocator.commands.scry.check_auth", _ok_check)
    monkeypatch.setattr("invocator.commands.scry.parse_repo", _ok_parse)
    monkeypatch.setattr(
        "invocator.commands.scry.get_default_branch",
        lambda repo: Result[str](
            success=False,
            error_code="REPO_NOT_FOUND",
            error_message="Repository not found",
        ),
    )
    result = runner.invoke(app, ["scry", "cost", "--repo", "owner/name"])
    assert result.exit_code == 2


def test_estimate_cost_sanity() -> None:
    counts = {
        "pulls": 1000,
        "issues": 500,
        "pulls_comments": 800,
        "issues_comments": 400,
        "commits": 1200,
    }
    estimate = estimate_cost(item_counts=counts, model="claude-sonnet-4-6")
    assert estimate.estimated_tokens > 0
    assert estimate.estimated_cost_usd_cents >= 0
    assert estimate.estimated_minutes >= 1
    assert estimate.per_resource == counts
