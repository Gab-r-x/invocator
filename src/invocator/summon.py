import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ValidationError
from rich.console import Console

from invocator.cache import (
    load_watermark,
    merge_by_id,
    repo_cache_dir,
    update_resource_watermark,
)
from invocator.config import Settings
from invocator.gh_client import GhSubprocessError, get_default_branch, run_gh
from invocator.models import (
    Commit,
    Issue,
    IssueComment,
    PullRequest,
    RepoRef,
    ReviewComment,
    SummonStats,
)
from invocator.result import Result

logger = logging.getLogger(__name__)

console = Console()
err_console = Console(stderr=True)

_BOT_LOGINS = frozenset({"dependabot[bot]", "renovate[bot]", "github-actions[bot]"})
_MERGE_COMMIT_PREFIXES = ("Merge pull request", "Merge branch")

_RESOURCE_PULLS = "pulls"
_RESOURCE_ISSUES = "issues"
_RESOURCE_COMMITS = "commits"
_RESOURCE_PR_REVIEW_COMMENTS = "pr_review_comments"
_RESOURCE_ISSUE_COMMENTS = "issue_comments"

_PR_NUMBER_FROM_URL = re.compile(r"/pulls/(\d+)")
_ISSUE_NUMBER_FROM_URL = re.compile(r"/issues/(\d+)")


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _effective_since(
    *,
    settings: Settings,
    repo: RepoRef,
    resource: str,
    since: datetime | None,
) -> datetime | None:
    watermark = load_watermark(settings=settings, repo=repo)
    per_resource = watermark.get("per_resource") or {}
    raw_wm = per_resource.get(resource)
    wm_dt: datetime | None = _parse_iso(raw_wm) if isinstance(raw_wm, str) else None
    if since is None:
        return wm_dt
    if wm_dt is None:
        return since
    return max(since, wm_dt)


def _paginate_jsonl(*, endpoint: str) -> list[dict]:
    raw = run_gh(["api", endpoint, "--jq", ".[]"], paginate=True)
    text = raw.decode("utf-8")
    items: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        items.append(json.loads(stripped))
    return items


def _is_bot_login(login: str | None) -> bool:
    return login is not None and login in _BOT_LOGINS


def _validate_items(
    *,
    raw_items: list[dict],
    transform: Callable[[dict], dict | None],
    model: type[BaseModel],
) -> list[dict]:
    validated: list[dict] = []
    for raw in raw_items:
        transformed = transform(raw)
        if transformed is None:
            continue
        try:
            instance = model(**transformed)
        except ValidationError as exc:
            item_id = raw.get("id") or raw.get("sha") or raw.get("number")
            logger.warning(
                "Skipping invalid %s item id=%s: %s",
                model.__name__,
                item_id,
                exc,
            )
            continue
        validated.append(instance.model_dump(mode="json"))
    return validated


def _transform_pull(raw: dict) -> dict | None:
    user = raw.get("user") or {}
    author_login = user.get("login")
    if author_login is None:
        return None
    labels = [lab.get("name") for lab in (raw.get("labels") or []) if lab.get("name")]
    merged_at = raw.get("merged_at")
    return {
        "id": raw["id"],
        "number": raw["number"],
        "title": raw.get("title") or "",
        "body": raw.get("body"),
        "state": raw.get("state") or "open",
        "labels": labels,
        "author_login": author_login,
        "merged_at_utc": merged_at,
        "created_at_utc": raw["created_at"],
        "updated_at_utc": raw["updated_at"],
    }


def _transform_issue(raw: dict) -> dict | None:
    user = raw.get("user") or {}
    author_login = user.get("login")
    if author_login is None:
        return None
    labels = [lab.get("name") for lab in (raw.get("labels") or []) if lab.get("name")]
    return {
        "id": raw["id"],
        "number": raw["number"],
        "title": raw.get("title") or "",
        "body": raw.get("body"),
        "state": raw.get("state") or "open",
        "labels": labels,
        "author_login": author_login,
        "created_at_utc": raw["created_at"],
        "updated_at_utc": raw["updated_at"],
    }


def _transform_commit(raw: dict) -> dict | None:
    commit_block = raw.get("commit") or {}
    message = commit_block.get("message") or ""
    author_block = raw.get("author") or {}
    author_login = author_block.get("login") if isinstance(author_block, dict) else None
    inner_author = commit_block.get("author") or {}
    authored_at = inner_author.get("date")
    if not authored_at:
        return None
    return {
        "sha": raw["sha"],
        "message": message,
        "author_login": author_login,
        "authored_at_utc": authored_at,
    }


def _transform_review_comment(raw: dict) -> dict | None:
    user = raw.get("user") or {}
    author_login = user.get("login")
    if author_login is None:
        return None
    pr_url = raw.get("pull_request_url") or ""
    match = _PR_NUMBER_FROM_URL.search(pr_url)
    if not match:
        return None
    return {
        "id": raw["id"],
        "pr_number": int(match.group(1)),
        "author_login": author_login,
        "body": raw.get("body") or "",
        "created_at_utc": raw["created_at"],
    }


def _transform_issue_comment(raw: dict) -> dict | None:
    user = raw.get("user") or {}
    author_login = user.get("login")
    if author_login is None:
        return None
    issue_url = raw.get("issue_url") or ""
    match = _ISSUE_NUMBER_FROM_URL.search(issue_url)
    if not match:
        return None
    return {
        "id": raw["id"],
        "issue_or_pr_number": int(match.group(1)),
        "author_login": author_login,
        "body": raw.get("body") or "",
        "created_at_utc": raw["created_at"],
    }


def _filter_bots_dict(items: list[dict], *, login_field: str) -> list[dict]:
    return [it for it in items if not _is_bot_login(it.get(login_field))]


def _filter_merge_commits(items: list[dict]) -> list[dict]:
    return [it for it in items if not (it.get("message") or "").startswith(_MERGE_COMMIT_PREFIXES)]


def _resource_path(*, settings: Settings, repo: RepoRef, resource: str) -> Path:
    return repo_cache_dir(settings=settings, repo=repo) / f"{resource}.jsonl"


def _fetch_pulls(
    *,
    settings: Settings,
    repo: RepoRef,
    since: datetime | None,
) -> int:
    effective = _effective_since(
        settings=settings, repo=repo, resource=_RESOURCE_PULLS, since=since
    )
    endpoint = (
        f"repos/{repo.owner}/{repo.name}/pulls" "?state=all&sort=updated&direction=asc&per_page=100"
    )
    raw_items = _paginate_jsonl(endpoint=endpoint)
    if effective is not None:
        filtered: list[dict] = []
        for it in raw_items:
            updated = it.get("updated_at")
            if not updated:
                continue
            if _parse_iso(updated) >= effective:
                filtered.append(it)
        raw_items = filtered
    validated = _validate_items(raw_items=raw_items, transform=_transform_pull, model=PullRequest)
    if settings.exclude_bots:
        validated = _filter_bots_dict(validated, login_field="author_login")
    path = _resource_path(settings=settings, repo=repo, resource=_RESOURCE_PULLS)
    merge_by_id(path=path, items=validated, id_field="id")
    update_resource_watermark(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_PULLS,
        timestamp_utc=datetime.now(timezone.utc),
    )
    return len(validated)


def _fetch_issues(
    *,
    settings: Settings,
    repo: RepoRef,
    since: datetime | None,
) -> int:
    effective = _effective_since(
        settings=settings, repo=repo, resource=_RESOURCE_ISSUES, since=since
    )
    endpoint = (
        f"repos/{repo.owner}/{repo.name}/issues"
        "?state=all&sort=updated&direction=asc&per_page=100"
    )
    if effective is not None:
        endpoint += f"&since={_to_iso_z(effective)}"
    raw_items = _paginate_jsonl(endpoint=endpoint)
    raw_items = [it for it in raw_items if "pull_request" not in it]
    validated = _validate_items(raw_items=raw_items, transform=_transform_issue, model=Issue)
    if settings.exclude_bots:
        validated = _filter_bots_dict(validated, login_field="author_login")
    path = _resource_path(settings=settings, repo=repo, resource=_RESOURCE_ISSUES)
    merge_by_id(path=path, items=validated, id_field="id")
    update_resource_watermark(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_ISSUES,
        timestamp_utc=datetime.now(timezone.utc),
    )
    return len(validated)


def _fetch_commits(
    *,
    settings: Settings,
    repo: RepoRef,
    default_branch: str,
    since: datetime | None,
) -> int:
    effective = _effective_since(
        settings=settings, repo=repo, resource=_RESOURCE_COMMITS, since=since
    )
    endpoint = f"repos/{repo.owner}/{repo.name}/commits" f"?sha={default_branch}&per_page=100"
    if effective is not None:
        endpoint += f"&since={_to_iso_z(effective)}"
    raw_items = _paginate_jsonl(endpoint=endpoint)
    validated = _validate_items(raw_items=raw_items, transform=_transform_commit, model=Commit)
    if settings.exclude_bots:
        validated = _filter_bots_dict(validated, login_field="author_login")
        validated = _filter_merge_commits(validated)
    path = _resource_path(settings=settings, repo=repo, resource=_RESOURCE_COMMITS)
    merge_by_id(path=path, items=validated, id_field="sha")
    update_resource_watermark(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_COMMITS,
        timestamp_utc=datetime.now(timezone.utc),
    )
    return len(validated)


def _fetch_pr_review_comments(
    *,
    settings: Settings,
    repo: RepoRef,
    since: datetime | None,
) -> int:
    effective = _effective_since(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_PR_REVIEW_COMMENTS,
        since=since,
    )
    endpoint = (
        f"repos/{repo.owner}/{repo.name}/pulls/comments" "?sort=updated&direction=asc&per_page=100"
    )
    if effective is not None:
        endpoint += f"&since={_to_iso_z(effective)}"
    raw_items = _paginate_jsonl(endpoint=endpoint)
    validated = _validate_items(
        raw_items=raw_items,
        transform=_transform_review_comment,
        model=ReviewComment,
    )
    if settings.exclude_bots:
        validated = _filter_bots_dict(validated, login_field="author_login")
    path = _resource_path(settings=settings, repo=repo, resource=_RESOURCE_PR_REVIEW_COMMENTS)
    merge_by_id(path=path, items=validated, id_field="id")
    update_resource_watermark(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_PR_REVIEW_COMMENTS,
        timestamp_utc=datetime.now(timezone.utc),
    )
    return len(validated)


def _fetch_issue_comments(
    *,
    settings: Settings,
    repo: RepoRef,
    since: datetime | None,
) -> int:
    effective = _effective_since(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_ISSUE_COMMENTS,
        since=since,
    )
    endpoint = (
        f"repos/{repo.owner}/{repo.name}/issues/comments" "?sort=updated&direction=asc&per_page=100"
    )
    if effective is not None:
        endpoint += f"&since={_to_iso_z(effective)}"
    raw_items = _paginate_jsonl(endpoint=endpoint)
    validated = _validate_items(
        raw_items=raw_items,
        transform=_transform_issue_comment,
        model=IssueComment,
    )
    if settings.exclude_bots:
        validated = _filter_bots_dict(validated, login_field="author_login")
    path = _resource_path(settings=settings, repo=repo, resource=_RESOURCE_ISSUE_COMMENTS)
    merge_by_id(path=path, items=validated, id_field="id")
    update_resource_watermark(
        settings=settings,
        repo=repo,
        resource=_RESOURCE_ISSUE_COMMENTS,
        timestamp_utc=datetime.now(timezone.utc),
    )
    return len(validated)


def summon_all(
    *,
    settings: Settings,
    repo: RepoRef,
    since: datetime | None = None,
) -> Result[SummonStats]:
    started_at = datetime.now(timezone.utc)

    branch_result = get_default_branch(repo=repo)
    if not branch_result.success or branch_result.data is None:
        return Result[SummonStats](
            success=False,
            error_code=branch_result.error_code or "DEFAULT_BRANCH_FAILED",
            error_message=branch_result.error_message,
            error_context=branch_result.error_context,
        )
    default_branch = branch_result.data

    try:
        console.print("[cyan]Fetching pulls...[/cyan]")
        pulls_count = _fetch_pulls(settings=settings, repo=repo, since=since)
        console.print(f"[green]✓[/green] Fetched {pulls_count} pulls")

        console.print("[cyan]Fetching issues...[/cyan]")
        issues_count = _fetch_issues(settings=settings, repo=repo, since=since)
        console.print(f"[green]✓[/green] Fetched {issues_count} issues")

        console.print("[cyan]Fetching commits...[/cyan]")
        commits_count = _fetch_commits(
            settings=settings,
            repo=repo,
            default_branch=default_branch,
            since=since,
        )
        console.print(f"[green]✓[/green] Fetched {commits_count} commits")

        console.print("[cyan]Fetching PR review comments...[/cyan]")
        pr_review_comments_count = _fetch_pr_review_comments(
            settings=settings, repo=repo, since=since
        )
        console.print(f"[green]✓[/green] Fetched {pr_review_comments_count} PR review comments")

        console.print("[cyan]Fetching issue comments...[/cyan]")
        issue_comments_count = _fetch_issue_comments(settings=settings, repo=repo, since=since)
        console.print(f"[green]✓[/green] Fetched {issue_comments_count} issue comments")
    except GhSubprocessError as exc:
        return Result[SummonStats](
            success=False,
            error_code="SUMMON_FETCH_FAILED",
            error_message=str(exc),
        ).add_context(key="returncode", value=str(exc.returncode))

    finished_at = datetime.now(timezone.utc)
    stats = SummonStats(
        pulls_count=pulls_count,
        issues_count=issues_count,
        commits_count=commits_count,
        pr_review_comments_count=pr_review_comments_count,
        issue_comments_count=issue_comments_count,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
    )
    return Result[SummonStats](success=True, data=stats)
