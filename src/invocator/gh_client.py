import json
import logging
import re
import subprocess
import time
from datetime import datetime, timezone

from invocator.models import RepoRef
from invocator.result import Result

logger = logging.getLogger(__name__)

_REPO_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_RATE_LIMIT_MAX_SLEEP_SECONDS = 600
_RATE_LIMIT_MAX_RETRIES = 3


class GhSubprocessError(RuntimeError):
    def __init__(self, *, returncode: int, stderr: bytes, args: list[str]) -> None:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        super().__init__(
            f"gh subprocess failed (exit={returncode}): {stderr_text or '<no stderr>'}"
        )
        self.returncode: int = returncode
        self.stderr: bytes = stderr
        self.args = tuple(args)  # type: ignore[assignment]


def check_gh_installed() -> Result[None]:
    try:
        completed = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
        )
    except FileNotFoundError:
        return Result[None](
            success=False,
            error_code="GH_NOT_INSTALLED",
            error_message="gh CLI not found. Install: https://cli.github.com/",
        )
    if completed.returncode != 0:
        return Result[None](
            success=False,
            error_code="GH_NOT_INSTALLED",
            error_message="gh CLI not found. Install: https://cli.github.com/",
        )
    return Result[None](success=True, data=None)


def check_auth() -> Result[None]:
    completed = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
    )
    if completed.returncode != 0:
        return Result[None](
            success=False,
            error_code="GH_NOT_AUTHENTICATED",
            error_message="gh is not authenticated. Run: gh auth login",
        )
    return Result[None](success=True, data=None)


def _is_rate_limited(*, returncode: int, stderr: bytes) -> bool:
    if returncode == 4:
        return True
    stderr_text = stderr.decode("utf-8", errors="replace").lower()
    return "rate limit" in stderr_text or "api rate limit exceeded" in stderr_text


def _read_rate_limit_reset_seconds() -> int:
    completed = subprocess.run(
        ["gh", "api", "rate_limit"],
        capture_output=True,
    )
    if completed.returncode != 0:
        raise GhSubprocessError(
            returncode=completed.returncode,
            stderr=completed.stderr,
            args=["gh", "api", "rate_limit"],
        )
    payload = json.loads(completed.stdout.decode("utf-8"))
    reset_epoch = int(payload["resources"]["core"]["reset"])
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    sleep_seconds = max(0, reset_epoch - now_epoch) + 1
    return sleep_seconds


def run_gh(args: list[str], *, paginate: bool = False) -> bytes:
    # `--paginate` is a flag of `gh api`, not of `gh` itself — it must come
    # AFTER `api`, not before. Insert it right after the `api` subcommand.
    invocation: list[str]
    if paginate and args and args[0] == "api":
        invocation = ["gh", "api", "--paginate"] + args[1:]
    elif paginate:
        invocation = ["gh"] + args + ["--paginate"]
    else:
        invocation = ["gh"] + args
    attempts = 0
    while True:
        completed = subprocess.run(
            invocation,
            capture_output=True,
        )
        if completed.returncode == 0:
            return completed.stdout
        if _is_rate_limited(returncode=completed.returncode, stderr=completed.stderr):
            if attempts >= _RATE_LIMIT_MAX_RETRIES:
                raise GhSubprocessError(
                    returncode=completed.returncode,
                    stderr=completed.stderr,
                    args=invocation,
                )
            sleep_seconds = _read_rate_limit_reset_seconds()
            if sleep_seconds > _RATE_LIMIT_MAX_SLEEP_SECONDS:
                raise GhSubprocessError(
                    returncode=completed.returncode,
                    stderr=completed.stderr,
                    args=invocation,
                )
            attempts += 1
            logger.warning(
                "gh rate-limited; sleeping %ds before retry %d/%d",
                sleep_seconds,
                attempts,
                _RATE_LIMIT_MAX_RETRIES,
            )
            time.sleep(sleep_seconds)
            continue
        raise GhSubprocessError(
            returncode=completed.returncode,
            stderr=completed.stderr,
            args=invocation,
        )


def parse_repo(value: str) -> Result[RepoRef]:
    raw = value.strip()
    if not raw:
        return Result[RepoRef](
            success=False,
            error_code="INVALID_REPO",
            error_message=f"Could not parse repo from: {value}",
        )

    candidate = raw
    https_prefix = "https://github.com/"
    http_prefix = "http://github.com/"
    ssh_prefix = "git@github.com:"
    if candidate.startswith(https_prefix):
        candidate = candidate[len(https_prefix) :]  # noqa: E203
    elif candidate.startswith(http_prefix):
        candidate = candidate[len(http_prefix) :]  # noqa: E203
    elif candidate.startswith(ssh_prefix):
        candidate = candidate[len(ssh_prefix) :]  # noqa: E203

    candidate = candidate.rstrip("/")
    git_suffix = ".git"
    if candidate.endswith(git_suffix):
        candidate = candidate[: -len(git_suffix)]  # noqa: E203

    parts = candidate.split("/")
    if len(parts) != 2:
        return Result[RepoRef](
            success=False,
            error_code="INVALID_REPO",
            error_message=f"Could not parse repo from: {value}",
        )

    owner, name = parts[0], parts[1]
    if not _REPO_NAME_PATTERN.match(owner) or not _REPO_NAME_PATTERN.match(name):
        return Result[RepoRef](
            success=False,
            error_code="INVALID_REPO",
            error_message=f"Could not parse repo from: {value}",
        )

    return Result[RepoRef](success=True, data=RepoRef(owner=owner, name=name))


def get_default_branch(*, repo: RepoRef) -> Result[str]:
    try:
        raw = run_gh(["api", f"repos/{repo.owner}/{repo.name}"])
    except GhSubprocessError as exc:
        stderr_text = exc.stderr.decode("utf-8", errors="replace")
        if exc.returncode in (1, 4) and "Not Found" in stderr_text:
            return Result[str](
                success=False,
                error_code="REPO_NOT_FOUND",
                error_message=f"Repository not found: {repo.owner}/{repo.name}",
            )
        raise

    payload = json.loads(raw.decode("utf-8"))
    return Result[str](success=True, data=payload["default_branch"])
