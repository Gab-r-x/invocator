from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from invocator.classify import classify
from invocator.commands.scry import render_cost_preview
from invocator.config import Settings, load_api_key
from invocator.gh_client import (
    check_auth,
    check_gh_installed,
    get_default_branch,
    parse_repo,
)
from invocator.models import Category, RepoRef
from invocator.result import Result
from invocator.summon import summon_all
from invocator.synthesize import synthesize_all

extract_app = typer.Typer(help="Extract spells — perform the full extraction ritual.")

console = Console()
err_console = Console(stderr=True)

# Exit code mapping (documented in code per phase 8 requirement):
#   0 -> success, or user-aborted at the cost confirmation prompt
#   1 -> mid-run failure (summon / classify / synthesize); cache from
#        earlier steps is preserved and the run can be safely retried
#   2 -> pre-check failure (gh missing/unauth'd, invalid/unknown repo,
#        no API key)
_EXIT_SUCCESS = 0
_EXIT_MID_RUN = 1
_EXIT_PRECHECK = 2

_PRECHECK_ERROR_CODES = frozenset(
    {
        "GH_NOT_INSTALLED",
        "GH_NOT_AUTHENTICATED",
        "INVALID_REPO",
        "REPO_NOT_FOUND",
        "NO_API_KEY",
        "CONFIG_READ_FAILED",
        "CONFIG_PARSE_FAILED",
    }
)


def _exit_code_for(*, error_code: str | None) -> int:
    if error_code is None:
        return _EXIT_MID_RUN
    if error_code in _PRECHECK_ERROR_CODES:
        return _EXIT_PRECHECK
    return _EXIT_MID_RUN


def _abort(*, result: Result, fallback_code: int) -> None:
    err_console.print(
        Panel(
            result.get_error_message() or "Unknown error",
            title="[red]invocator extract wisdom — aborted[/red]",
            border_style="red",
        )
    )
    code = (
        _exit_code_for(error_code=result.error_code)
        if result.error_code is not None
        else fallback_code
    )
    raise typer.Exit(code=code)


def _parse_since(*, value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc)


def _clear_watermark(*, settings: Settings, repo: RepoRef) -> None:
    watermark_path = settings.cache_dir / f"{repo.owner}__{repo.name}" / "watermark.json"
    if watermark_path.exists():
        watermark_path.unlink()


def _count_bullets(*, md_path: Path) -> int:
    # Different category templates use different markers:
    #   - rules.md uses dash bullets ("- ")
    #   - prevencoes / patterns / decisions use H3 sections ("### ")
    #   - glossary uses "**Term**" lines
    # Count any of them so the terminal display matches the file content.
    if not md_path.exists():
        return 0
    count = 0
    for raw_line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if (
            stripped.startswith("- ")
            or stripped.startswith("* ")
            or stripped.startswith("### ")
            or stripped.startswith("**")
        ):
            count += 1
    return count


@extract_app.command("wisdom")
def extract_wisdom(
    repo: str = typer.Option(..., "--repo", help="GitHub repo: owner/name or URL."),
    since: str | None = typer.Option(None, "--since", help="ISO date (YYYY-MM-DD) lower bound."),
    out: Path = typer.Option(Path("./learnings"), "--out", help="Output directory."),
    cache_dir: Path = typer.Option(Path("./.cache/invocator"), "--cache-dir", help="Cache root."),
    model: str = typer.Option(
        "claude-sonnet-4-6", "--model", help="Anthropic model for synthesis."
    ),
    top_k: int = typer.Option(500, "--top-k", help="Max classified items per category."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip LLM; write classified dumps."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip cost confirmation prompt."),
    force_refetch: bool = typer.Option(False, "--force-refetch", help="Ignore cache, refetch all."),
) -> None:
    gh_check = check_gh_installed()
    if not gh_check.success:
        _abort(result=gh_check, fallback_code=_EXIT_PRECHECK)

    auth_check = check_auth()
    if not auth_check.success:
        _abort(result=auth_check, fallback_code=_EXIT_PRECHECK)

    parsed = parse_repo(value=repo)
    if not parsed.success or parsed.data is None:
        _abort(result=parsed, fallback_code=_EXIT_PRECHECK)
        return
    repo_ref = parsed.data

    if not dry_run:
        key_result = load_api_key()
        if not key_result.success:
            err_console.print(
                Panel(
                    (key_result.get_error_message() or "No Anthropic API key configured.")
                    + "\n\nRun: [bold]invocator forge key[/bold]",
                    title="[red]invocator extract wisdom — aborted[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(code=_EXIT_PRECHECK)

    branch_result = get_default_branch(repo=repo_ref)
    if not branch_result.success or branch_result.data is None:
        _abort(result=branch_result, fallback_code=_EXIT_PRECHECK)
        return
    default_branch = branch_result.data

    render_cost_preview(
        repo=repo_ref,
        default_branch=default_branch,
        model=model,
        since=since,
    )

    if not yes:
        proceed = typer.confirm("Proceed with extraction?", default=True)
        if not proceed:
            console.print("[yellow]Aborted by user.[/yellow]")
            raise typer.Exit(code=_EXIT_SUCCESS)

    settings = Settings(
        cache_dir=cache_dir,
        out_dir=out,
        model=model,
        top_k_per_category=top_k,
    )

    since_dt = _parse_since(value=since)

    if force_refetch:
        _clear_watermark(settings=settings, repo=repo_ref)

    console.print("[cyan]Summoning corpus from GitHub...[/cyan]")
    summon_result = summon_all(settings=settings, repo=repo_ref, since=since_dt)
    if not summon_result.success:
        _abort(result=summon_result, fallback_code=_EXIT_MID_RUN)
        return

    console.print("[cyan]Transmuting (classifying) cached items...[/cyan]")
    classify_result = classify(settings=settings, repo=repo_ref, top_k=top_k)
    if not classify_result.success or classify_result.data is None:
        _abort(result=classify_result, fallback_code=_EXIT_MID_RUN)
        return

    console.print("[cyan]Inscribing markdown via synthesis...[/cyan]")
    synth_result = synthesize_all(
        settings=settings,
        repo=repo_ref,
        model=model,
        dry_run=dry_run,
        force=False,
    )
    if not synth_result.success or synth_result.data is None:
        _abort(result=synth_result, fallback_code=_EXIT_MID_RUN)
        return

    synth_stats = synth_result.data
    total_dollars = synth_stats.total_cost_usd_cents / 100

    console.print()
    console.print(f"[bold green]✓ Done.[/bold green] Output written to [bold]{out}[/bold]")
    for category in Category:
        md_path = out / f"{category.value}.md"
        bullets = _count_bullets(md_path=md_path)
        console.print(f"  [cyan]{category.value}.md[/cyan]: {bullets} entries  ({md_path})")
    index_path = out / "INDEX.md"
    console.print(f"  [cyan]INDEX.md[/cyan]: {index_path}")
    breakdown = (
        f"[cyan]synthesized:[/cyan] {synth_stats.categories_synthesized}   "
        f"[cyan]cached:[/cyan] {synth_stats.categories_cached}   "
        f"[cyan]skipped (empty):[/cyan] {synth_stats.categories_skipped_empty}"
    )
    if synth_stats.categories_dry_run_dumped:
        breakdown += f"   [cyan]dry-run dumps:[/cyan] {synth_stats.categories_dry_run_dumped}"
    console.print(breakdown)
    console.print(f"[cyan]Total cost:[/cyan] ${total_dollars:.2f}")
