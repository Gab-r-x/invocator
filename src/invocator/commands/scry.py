import json
import re

import typer
from rich.console import Console
from rich.table import Table

from invocator.gh_client import (
    GhSubprocessError,
    check_auth,
    check_gh_installed,
    get_default_branch,
    parse_repo,
    run_gh,
)
from invocator.models import (
    MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION,
    CostEstimate,
    RepoRef,
)
from invocator.result import Result

scry_app = typer.Typer(help="Scry spells — gaze ahead at cost before the ritual.")

console = Console()
err_console = Console(stderr=True)

# Heuristic constants. See estimate_cost docstring/comments for rationale.
_SIGNAL_RATIO = 0.30
_TOKENS_PER_ITEM = 200
_NUM_CATEGORIES = 5
_DEFAULT_PRICING_CENTS_PER_MILLION = 300

_LINK_LAST_PAGE_PATTERN = re.compile(r'<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"')


def probe_endpoint(*, endpoint: str) -> Result[int]:
    # gh -i emits HTTP headers followed by a blank line, then the JSON body.
    # We probe with per_page=1 so the last-page number IS the item count.
    # If there's no Link header, there's a single page — estimate from the
    # JSON array length of the body.
    separator = "&" if "?" in endpoint else "?"
    full_endpoint = f"{endpoint}{separator}per_page=1"
    try:
        raw = run_gh(["api", "-i", full_endpoint])
    except GhSubprocessError as exc:
        stderr_text = exc.stderr.decode("utf-8", errors="replace")
        result: Result[int] = Result[int](
            success=False,
            error_code="PROBE_FAILED",
            error_message=f"gh probe failed for {endpoint}: {stderr_text.strip()}",
        )
        result.add_context(key="endpoint", value=endpoint)
        result.add_context(key="returncode", value=str(exc.returncode))
        if "Not Found" in stderr_text:
            result.add_context(key="reason", value="not_found")
        return result

    text = raw.decode("utf-8", errors="replace")
    header_block, _, body = text.partition("\n\n")
    if not body:
        header_block, _, body = text.partition("\r\n\r\n")

    link_header: str | None = None
    for line in header_block.splitlines():
        if line.lower().startswith("link:"):
            link_header = line.split(":", 1)[1].strip()
            break

    if link_header:
        match = _LINK_LAST_PAGE_PATTERN.search(link_header)
        if match:
            last_page = int(match.group(1))
            return Result[int](success=True, data=last_page)

    body_stripped = body.strip()
    if not body_stripped:
        return Result[int](success=True, data=0)
    try:
        payload = json.loads(body_stripped)
    except json.JSONDecodeError:
        return Result[int](success=True, data=0)
    if isinstance(payload, list):
        return Result[int](success=True, data=len(payload))
    return Result[int](success=True, data=0)


def estimate_cost(*, item_counts: dict[str, int], model: str) -> CostEstimate:
    # Heuristic: empirically ~30% of raw GitHub items carry signal worth
    # classifying. Each classified item contributes ~200 input tokens to the
    # synthesis corpus. Five category prompts share the same corpus bundle, so
    # total_tokens is the corpus size (not multiplied by category count —
    # caching makes the per-category overhead negligible).
    total_items = sum(item_counts.values())
    classified_items = total_items * _SIGNAL_RATIO
    total_tokens = int(classified_items * _TOKENS_PER_ITEM)

    cost_per_million_cents = MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION.get(
        model, _DEFAULT_PRICING_CENTS_PER_MILLION
    )
    estimated_cost_usd_cents = int(round((total_tokens / 1_000_000) * cost_per_million_cents))
    estimated_minutes = max(1, int(round((total_tokens / 1_000_000) * 2)))

    return CostEstimate(
        estimated_tokens=total_tokens,
        estimated_cost_usd_cents=estimated_cost_usd_cents,
        estimated_minutes=estimated_minutes,
        per_resource=dict(item_counts),
    )


def render_cost_preview(
    *,
    repo: RepoRef,
    default_branch: str,
    model: str,
    since: str | None = None,
) -> CostEstimate:
    # Shared probe + table render between `scry cost` and `extract wisdom`.
    # Pre-checks (gh installed, auth, parse_repo, default branch) must be
    # performed by the caller — this helper assumes a valid RepoRef and branch.
    endpoints = _build_probe_endpoints(repo=repo, default_branch=default_branch)
    item_counts: dict[str, int] = {}
    failed_resources: dict[str, str] = {}

    for resource_name, endpoint in endpoints:
        probed = probe_endpoint(endpoint=endpoint)
        if probed.success and probed.data is not None:
            item_counts[resource_name] = probed.data
            continue
        if probed.error_context.get("reason") == "not_found":
            item_counts[resource_name] = 0
            continue
        failed_resources[resource_name] = probed.get_error_message()

    estimate = estimate_cost(item_counts=item_counts, model=model)

    table = Table(
        title=f"Scry cost — {repo.owner}/{repo.name} (model={model})",
        show_header=True,
    )
    table.add_column("Resource")
    table.add_column("Estimated items", justify="right")

    for resource_name, _endpoint in endpoints:
        if resource_name in item_counts:
            table.add_row(resource_name, str(item_counts[resource_name]))
        else:
            table.add_row(resource_name, "—")

    total_items = sum(item_counts.values())
    table.add_row("[bold]total[/bold]", f"[bold]{total_items}[/bold]")

    console.print(table)

    if since is not None:
        console.print(f"[dim]--since {since} provided (informational only in this phase)[/dim]")

    dollars = estimate.estimated_cost_usd_cents / 100
    console.print(
        f"[cyan]Estimated tokens:[/cyan] {estimate.estimated_tokens:,}   "
        f"[cyan]Cost:[/cyan] ${dollars:.2f}   "
        f"[cyan]Wall time:[/cyan] ~{estimate.estimated_minutes} min"
    )

    if failed_resources:
        for resource_name, message in failed_resources.items():
            err_console.print(f"[yellow]![/yellow] probe failed for {resource_name}: {message}")

    return estimate


def _build_probe_endpoints(*, repo: RepoRef, default_branch: str) -> list[tuple[str, str]]:
    base = f"repos/{repo.owner}/{repo.name}"
    return [
        ("pulls", f"{base}/pulls?state=all"),
        ("issues", f"{base}/issues?state=all"),
        ("pulls_comments", f"{base}/pulls/comments"),
        ("issues_comments", f"{base}/issues/comments"),
        ("commits", f"{base}/commits?sha={default_branch}"),
    ]


@scry_app.command("cost")
def scry_cost(
    repo: str = typer.Option(..., "--repo", help="GitHub repo: owner/name or URL."),
    model: str = typer.Option(
        "claude-sonnet-4-6", "--model", help="Anthropic model for cost estimation."
    ),
    since: str | None = typer.Option(
        None, "--since", help="ISO date (YYYY-MM-DD) lower bound (currently informational)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    gh_check = check_gh_installed()
    if not gh_check.success:
        err_console.print(f"[red]✗[/red] {gh_check.get_error_message()}")
        raise typer.Exit(code=2)

    auth_check = check_auth()
    if not auth_check.success:
        err_console.print(f"[red]✗[/red] {auth_check.get_error_message()}")
        raise typer.Exit(code=2)

    parsed = parse_repo(value=repo)
    if not parsed.success or parsed.data is None:
        err_console.print(f"[red]✗[/red] {parsed.get_error_message()}")
        raise typer.Exit(code=2)
    repo_ref = parsed.data

    branch_result = get_default_branch(repo=repo_ref)
    if not branch_result.success or branch_result.data is None:
        err_console.print(f"[red]✗[/red] {branch_result.get_error_message()}")
        raise typer.Exit(code=2)
    default_branch = branch_result.data

    if json_output:
        endpoints = _build_probe_endpoints(repo=repo_ref, default_branch=default_branch)
        item_counts: dict[str, int] = {}
        for resource_name, endpoint in endpoints:
            probed = probe_endpoint(endpoint=endpoint)
            if probed.success and probed.data is not None:
                item_counts[resource_name] = probed.data
                continue
            if probed.error_context.get("reason") == "not_found":
                item_counts[resource_name] = 0
        estimate = estimate_cost(item_counts=item_counts, model=model)
        # STANDARDS Rule 13 exception: --json mode emits bare JSON on stdout
        # for machine consumption. Using console.print_json keeps output
        # routed through Rich while emitting clean JSON without markup.
        console.print_json(json.dumps(estimate.model_dump()))
        return

    render_cost_preview(
        repo=repo_ref,
        default_branch=default_branch,
        model=model,
        since=since,
    )
