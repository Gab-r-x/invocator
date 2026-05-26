import json
import subprocess
from datetime import datetime, timezone

import pytest

from invocator import gh_client
from invocator.gh_client import (
    GhSubprocessError,
    check_auth,
    check_gh_installed,
    get_default_branch,
    parse_repo,
    run_gh,
)
from invocator.models import RepoRef


def _completed(
    *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_parse_repo_owner_name() -> None:
    result = parse_repo("owner/name")
    assert result.success is True
    assert result.data == RepoRef(owner="owner", name="name")


def test_parse_repo_https_url() -> None:
    result = parse_repo("https://github.com/owner/name")
    assert result.success is True
    assert result.data == RepoRef(owner="owner", name="name")


def test_parse_repo_https_url_with_git_suffix() -> None:
    result = parse_repo("https://github.com/owner/name.git")
    assert result.success is True
    assert result.data == RepoRef(owner="owner", name="name")


def test_parse_repo_ssh_form() -> None:
    result = parse_repo("git@github.com:owner/name.git")
    assert result.success is True
    assert result.data == RepoRef(owner="owner", name="name")


def test_parse_repo_garbage_returns_invalid_repo() -> None:
    result = parse_repo("garbage")
    assert result.success is False
    assert result.error_code == "INVALID_REPO"


def test_parse_repo_owner_name_with_space_invalid() -> None:
    result = parse_repo("owner/name with space")
    assert result.success is False
    assert result.error_code == "INVALID_REPO"


def test_check_gh_installed_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=0, stdout=b"gh version 2.0\n"),
    )
    result = check_gh_installed()
    assert result.success is True


def test_check_gh_installed_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **kw: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError()

    monkeypatch.setattr(gh_client.subprocess, "run", boom)
    result = check_gh_installed()
    assert result.success is False
    assert result.error_code == "GH_NOT_INSTALLED"


def test_check_gh_installed_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=1, stderr=b"nope"),
    )
    result = check_gh_installed()
    assert result.success is False
    assert result.error_code == "GH_NOT_INSTALLED"


def test_check_auth_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=0),
    )
    result = check_auth()
    assert result.success is True


def test_check_auth_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=1, stderr=b"not logged in"),
    )
    result = check_auth()
    assert result.success is False
    assert result.error_code == "GH_NOT_AUTHENTICATED"


def test_run_gh_returns_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=0, stdout=b"{}"),
    )
    assert run_gh(["api", "repos/a/b"]) == b"{}"


def test_run_gh_paginate_inserts_flag_after_api(monkeypatch: pytest.MonkeyPatch) -> None:
    # --paginate is a flag of `gh api`, not of `gh` itself; it must come
    # AFTER the `api` subcommand or gh exits with "unknown flag".
    calls: list[list[str]] = []

    def fake_run(invocation: list[str], **kw: object) -> subprocess.CompletedProcess:
        calls.append(invocation)
        return _completed(returncode=0, stdout=b"[]")

    monkeypatch.setattr(gh_client.subprocess, "run", fake_run)
    run_gh(["api", "repos/a/b/pulls"], paginate=True)
    assert calls == [["gh", "api", "--paginate", "repos/a/b/pulls"]]


def test_run_gh_nonzero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=2, stderr=b"boom"),
    )
    with pytest.raises(GhSubprocessError) as exc:
        run_gh(["api", "repos/a/b"])
    assert exc.value.returncode == 2
    assert exc.value.stderr == b"boom"


def test_run_gh_rate_limit_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    future_reset = int(datetime.now(timezone.utc).timestamp()) + 2
    rate_limit_payload = json.dumps({"resources": {"core": {"reset": future_reset}}}).encode(
        "utf-8"
    )
    responses = [
        _completed(returncode=4, stderr=b"API rate limit exceeded"),
        _completed(returncode=0, stdout=rate_limit_payload),
        _completed(returncode=0, stdout=b"DONE"),
    ]
    sleep_calls: list[float] = []

    def fake_run(invocation: list[str], **kw: object) -> subprocess.CompletedProcess:
        return responses.pop(0)

    monkeypatch.setattr(gh_client.subprocess, "run", fake_run)
    monkeypatch.setattr(gh_client.time, "sleep", lambda s: sleep_calls.append(s))

    assert run_gh(["api", "repos/a/b"]) == b"DONE"
    assert len(sleep_calls) == 1


def test_run_gh_rate_limit_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    future_reset = int(datetime.now(timezone.utc).timestamp()) + 2
    rate_limit_payload = json.dumps({"resources": {"core": {"reset": future_reset}}}).encode(
        "utf-8"
    )

    def fake_run(invocation: list[str], **kw: object) -> subprocess.CompletedProcess:
        if invocation[:3] == ["gh", "api", "rate_limit"]:
            return _completed(returncode=0, stdout=rate_limit_payload)
        return _completed(returncode=4, stderr=b"API rate limit exceeded")

    monkeypatch.setattr(gh_client.subprocess, "run", fake_run)
    monkeypatch.setattr(gh_client.time, "sleep", lambda s: None)

    with pytest.raises(GhSubprocessError):
        run_gh(["api", "repos/a/b"])


def test_get_default_branch_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=0, stdout=b'{"default_branch": "main"}'),
    )
    result = get_default_branch(repo=RepoRef(owner="a", name="b"))
    assert result.success is True
    assert result.data == "main"


def test_get_default_branch_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh_client.subprocess,
        "run",
        lambda *a, **kw: _completed(returncode=1, stderr=b"gh: Not Found (HTTP 404)"),
    )
    result = get_default_branch(repo=RepoRef(owner="a", name="b"))
    assert result.success is False
    assert result.error_code == "REPO_NOT_FOUND"
