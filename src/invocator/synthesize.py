import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from anthropic import Anthropic
from rich.console import Console

from invocator import cache
from invocator.config import Settings
from invocator.models import (
    MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION,
    MODEL_PRICING_OUTPUT_USD_CENTS_PER_MILLION,
    Category,
    ClassifiedItem,
    RepoRef,
    SynthesisOutput,
    SynthesisStats,
)
from invocator.prompts import CATEGORY_TO_INSTRUCTION, SYSTEM_PROMPT
from invocator.result import Result

logger = logging.getLogger(__name__)

console = Console()
err_console = Console(stderr=True)

_TOKEN_SOFT_CAP = 200_000
_DEFAULT_INPUT_PRICE_CENTS_PER_MILLION = 300
_DEFAULT_OUTPUT_PRICE_CENTS_PER_MILLION = 1500
_LOCAL_TOKEN_DIVISOR = 4
_MAX_OUTPUT_TOKENS = 8000

_CATEGORY_FILENAMES: dict[Category, str] = {
    Category.RULES: "rules.md",
    Category.PREVENCOES: "prevencoes.md",
    Category.PATTERNS: "patterns.md",
    Category.DECISIONS: "decisions.md",
    Category.GLOSSARY: "glossary.md",
}


def _get_client(*, api_key: str) -> Anthropic:
    return Anthropic(api_key=api_key)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _escape_snippet(*, snippet: str) -> str:
    return snippet.replace("\\", "\\\\").replace('"', '\\"')


def build_corpus(*, classified_items: list[ClassifiedItem]) -> str:
    lines: list[str] = []
    for index, item in enumerate(classified_items, start=1):
        snippet = _escape_snippet(snippet=item.snippet)
        signals = ",".join(item.signals) if item.signals else ""
        lines.append(f'[#{index}] source={item.source_ref} snippet="{snippet}" signals=[{signals}]')
    return "\n".join(lines)


def count_tokens_estimate(*, system: str, corpus: str) -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            client = _get_client(api_key=api_key)
            result = client.messages.count_tokens(
                model="claude-haiku-4-5",
                system=system,
                messages=[{"role": "user", "content": corpus}],
            )
            return int(result.input_tokens)
        except AttributeError:
            pass
        except anthropic.APIError:
            pass
        except Exception:  # noqa: BLE001 — fall back to local estimate on any SDK error
            pass
    return (len(system) + len(corpus)) // _LOCAL_TOKEN_DIVISOR


def _input_price_cents_per_million(*, model: str) -> int:
    return MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION.get(
        model, _DEFAULT_INPUT_PRICE_CENTS_PER_MILLION
    )


def _output_price_cents_per_million(*, model: str) -> int:
    return MODEL_PRICING_OUTPUT_USD_CENTS_PER_MILLION.get(
        model, _DEFAULT_OUTPUT_PRICE_CENTS_PER_MILLION
    )


def _compute_cost_usd_cents(
    *,
    model: str,
    input_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    output_tokens: int,
) -> int:
    input_rate = _input_price_cents_per_million(model=model)
    output_rate = _output_price_cents_per_million(model=model)
    # Cache writes: ~1.25x base input; cache reads: ~0.1x base input.
    input_cost = input_tokens * input_rate
    cache_write_cost = int(cache_creation_input_tokens * input_rate * 1.25)
    cache_read_cost = int(cache_read_input_tokens * input_rate * 0.10)
    output_cost = output_tokens * output_rate
    total_micro_cents = input_cost + cache_write_cost + cache_read_cost + output_cost
    return total_micro_cents // 1_000_000


def _format_tokens(*, n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _get_usage_field(*, usage: Any, name: str) -> int:
    value = getattr(usage, name, None) if usage is not None else None
    if value is None:
        return 0
    return int(value)


def log_usage(*, response: Any, category: Category, model: str = "claude-sonnet-4-6") -> int:
    usage = getattr(response, "usage", None)
    input_tokens = _get_usage_field(usage=usage, name="input_tokens")
    cache_creation_input_tokens = _get_usage_field(usage=usage, name="cache_creation_input_tokens")
    cache_read_input_tokens = _get_usage_field(usage=usage, name="cache_read_input_tokens")
    output_tokens = _get_usage_field(usage=usage, name="output_tokens")

    cost_usd_cents = _compute_cost_usd_cents(
        model=model,
        input_tokens=input_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        output_tokens=output_tokens,
    )
    cost_dollars = cost_usd_cents / 100.0
    err_console.print(
        f"[dim]{category.value}:[/dim] "
        f"in={_format_tokens(n=input_tokens)} "
        f"cache_read={_format_tokens(n=cache_read_input_tokens)} "
        f"cache_write={_format_tokens(n=cache_creation_input_tokens)} "
        f"out={_format_tokens(n=output_tokens)} "
        f"→ ${cost_dollars:.2f}"
    )
    return cost_usd_cents


def _extract_markdown(*, response: Any) -> str:
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def synthesize_category(
    *,
    client: Anthropic,
    model: str,
    category: Category,
    corpus: str,
    instruction: str,
) -> Result[SynthesisOutput]:
    try:
        response = client.messages.create(
            model=model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": corpus,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": instruction},
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        return Result[SynthesisOutput](
            success=False,
            error_code="ANTHROPIC_API_ERROR",
            error_message=str(exc),
        ).add_context(key="category", value=category.value)

    cost_usd_cents = log_usage(response=response, category=category, model=model)
    usage = getattr(response, "usage", None)
    markdown = _extract_markdown(response=response)

    output = SynthesisOutput(
        category=category,
        markdown=markdown,
        input_tokens=_get_usage_field(usage=usage, name="input_tokens"),
        cache_creation_input_tokens=_get_usage_field(
            usage=usage, name="cache_creation_input_tokens"
        ),
        cache_read_input_tokens=_get_usage_field(usage=usage, name="cache_read_input_tokens"),
        output_tokens=_get_usage_field(usage=usage, name="output_tokens"),
        cost_usd_cents=cost_usd_cents,
    )
    return Result[SynthesisOutput](success=True, data=output)


def _sha256_hex(*, text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_cache_dir(*, out_dir: Path) -> Path:
    path = out_dir / ".cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hash_file(*, out_dir: Path, category: Category) -> Path:
    return _hash_cache_dir(out_dir=out_dir) / f"{category.value}.hash"


def _category_md_path(*, out_dir: Path, category: Category) -> Path:
    return out_dir / _CATEGORY_FILENAMES[category]


def _write_atomic(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp_path, path)


def _load_classified(
    *, settings: Settings, repo: RepoRef, category: Category
) -> list[ClassifiedItem]:
    repo_dir = cache.repo_cache_dir(settings=settings, repo=repo)
    path = repo_dir / "classified" / f"{category.value}.jsonl"
    rows = cache.read_jsonl(path)
    items: list[ClassifiedItem] = []
    for row in rows:
        items.append(ClassifiedItem.model_validate(row))
    return items


def _render_dry_run_markdown(*, category: Category, items: list[ClassifiedItem]) -> str:
    lines: list[str] = [f"# {category.value} (dry-run dump)", ""]
    for item in items:
        signals = ", ".join(item.signals) if item.signals else "none"
        snippet = item.snippet.replace("\n", " ")
        lines.append(f'- [{item.source_ref}] (signals: {signals}) "{snippet}"')
    return "\n".join(lines) + "\n"


_BULLET_LINE_RE = re.compile(r"^\s*(-\s|###\s)", re.MULTILINE)


def _count_bullets(*, markdown: str) -> int:
    return len(_BULLET_LINE_RE.findall(markdown))


def _render_index_markdown(
    *,
    repo: RepoRef,
    model: str,
    timestamp_utc: datetime,
    total_classified: int,
    per_category_counts: dict[Category, int],
    total_cost_usd_cents: int,
    categories_cached: int,
) -> str:
    cost_dollars = total_cost_usd_cents / 100.0
    iso_ts = timestamp_utc.isoformat().replace("+00:00", "Z")
    lines: list[str] = [
        f"# Learnings — {repo.owner}/{repo.name}",
        "",
        f"Synthesized {iso_ts} from {total_classified} classified items.",
        "",
        "## Files",
        "",
        f"- [rules.md](rules.md) — {per_category_counts.get(Category.RULES, 0)} entries",
        f"- [prevencoes.md](prevencoes.md) — "
        f"{per_category_counts.get(Category.PREVENCOES, 0)} entries",
        f"- [patterns.md](patterns.md) — {per_category_counts.get(Category.PATTERNS, 0)} entries",
        f"- [decisions.md](decisions.md) — "
        f"{per_category_counts.get(Category.DECISIONS, 0)} entries",
        f"- [glossary.md](glossary.md) — {per_category_counts.get(Category.GLOSSARY, 0)} entries",
        "",
        "## Run",
        "",
        f"- Repo: {repo.owner}/{repo.name}",
        f"- Model: {model}",
        f"- Total cost: ${cost_dollars:.2f}",
        f"- Cached categories: {categories_cached}/5",
        "",
    ]
    return "\n".join(lines)


# INDEX.md is rendered deterministically (no LLM call) in v1. Synthesis adds no
# value here — counts, timestamps, and repo info are all known from local state,
# so paying tokens to format them would be pure waste.
def _set_cost_field(*, stats: SynthesisStats, category: Category, cost_usd_cents: int) -> None:
    if category is Category.RULES:
        stats.rules_cost_usd_cents = cost_usd_cents
    elif category is Category.PREVENCOES:
        stats.prevencoes_cost_usd_cents = cost_usd_cents
    elif category is Category.PATTERNS:
        stats.patterns_cost_usd_cents = cost_usd_cents
    elif category is Category.DECISIONS:
        stats.decisions_cost_usd_cents = cost_usd_cents
    elif category is Category.GLOSSARY:
        stats.glossary_cost_usd_cents = cost_usd_cents


def synthesize_all(
    *,
    settings: Settings,
    repo: RepoRef,
    model: str,
    dry_run: bool = False,
    force: bool = False,
) -> Result[SynthesisStats]:
    started_at = _utc_now()
    out_dir = settings.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = SynthesisStats(
        started_at_utc=started_at,
        finished_at_utc=started_at,
    )

    per_category_counts: dict[Category, int] = {}
    total_classified = 0

    client: Anthropic | None = None
    if not dry_run:
        from invocator.config import load_api_key

        api_key_result = load_api_key()
        if not api_key_result.success or not api_key_result.data:
            return Result[SynthesisStats](
                success=False,
                error_code=api_key_result.error_code or "NO_API_KEY",
                error_message=api_key_result.error_message
                or "No Anthropic API key available for synthesis.",
            )
        client = _get_client(api_key=api_key_result.data)

    for category in Category:
        items = _load_classified(settings=settings, repo=repo, category=category)
        total_classified += len(items)
        md_path = _category_md_path(out_dir=out_dir, category=category)

        if dry_run:
            markdown = _render_dry_run_markdown(category=category, items=items)
            _write_atomic(path=md_path, text=markdown)
            per_category_counts[category] = _count_bullets(markdown=markdown)
            stats.categories_synthesized += 1
            continue

        corpus = build_corpus(classified_items=items)
        bundle_hash = _sha256_hex(text=corpus)
        hash_path = _hash_file(out_dir=out_dir, category=category)

        stored_hash: str | None = None
        if hash_path.exists():
            stored_hash = hash_path.read_text(encoding="utf-8").strip() or None

        if not force and stored_hash == bundle_hash and md_path.exists():
            stats.categories_cached += 1
            existing_md = md_path.read_text(encoding="utf-8")
            per_category_counts[category] = _count_bullets(markdown=existing_md)
            err_console.print(
                f"[dim]{category.value}:[/dim] [green]cached[/green] (hash match, skipped LLM)"
            )
            continue

        estimated_tokens = count_tokens_estimate(system=SYSTEM_PROMPT, corpus=corpus)
        if estimated_tokens > _TOKEN_SOFT_CAP and not force:
            err_console.print(
                f"[yellow]{category.value}:[/yellow] corpus too large "
                f"({estimated_tokens} tokens > {_TOKEN_SOFT_CAP}); skipping."
                " Use --force to override."
            )
            continue

        assert client is not None
        instruction = CATEGORY_TO_INSTRUCTION[category]
        result = synthesize_category(
            client=client,
            model=model,
            category=category,
            corpus=corpus,
            instruction=instruction,
        )
        if not result.success or result.data is None:
            err_console.print(
                f"[red]✗[/red] {category.value} synthesis failed: {result.get_error_message()}"
            )
            continue

        output = result.data
        _write_atomic(path=md_path, text=output.markdown)
        hash_path.write_text(bundle_hash, encoding="utf-8")
        per_category_counts[category] = _count_bullets(markdown=output.markdown)
        stats.categories_synthesized += 1
        _set_cost_field(stats=stats, category=category, cost_usd_cents=output.cost_usd_cents)
        stats.total_cost_usd_cents += output.cost_usd_cents

    finished_at = _utc_now()
    stats.finished_at_utc = finished_at

    index_markdown = _render_index_markdown(
        repo=repo,
        model=model,
        timestamp_utc=finished_at,
        total_classified=total_classified,
        per_category_counts=per_category_counts,
        total_cost_usd_cents=stats.total_cost_usd_cents,
        categories_cached=stats.categories_cached,
    )
    _write_atomic(path=out_dir / "INDEX.md", text=index_markdown)

    return Result[SynthesisStats](success=True, data=stats)
