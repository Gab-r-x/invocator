import hashlib
import logging
import os
import re
from collections import Counter
from pathlib import Path

from rich.console import Console

from invocator.cache import read_jsonl, repo_cache_dir
from invocator.config import Settings
from invocator.models import Category, ClassifiedItem, ClassifyStats, RepoRef
from invocator.result import Result
from invocator.rules.adr import classify_adr
from invocator.rules.conventional import classify_conventional
from invocator.rules.labels import classify_labels
from invocator.rules.review_cues import classify_review_cues

logger = logging.getLogger(__name__)

console = Console()
err_console = Console(stderr=True)

_ITEM_TYPES = ("pull", "issue", "commit", "review_comment", "issue_comment")

_RESOURCE_FILENAMES: dict[str, str] = {
    "pull": "pulls.jsonl",
    "issue": "issues.jsonl",
    "commit": "commits.jsonl",
    "review_comment": "pr_review_comments.jsonl",
    "issue_comment": "issue_comments.jsonl",
}

_WHITESPACE_RE = re.compile(r"\s+")

_BACKTICK_RE = re.compile(r"`([^`\n]{2,80})`")
_CAPITALIZED_PHRASE_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)+\b")

_GLOSSARY_FREQUENCY_THRESHOLD = 3
_GLOSSARY_SOURCE_REF = "corpus"

_CATEGORY_FIELD_MAP: dict[Category, str] = {
    Category.RULES: "rules_count",
    Category.PREVENCOES: "prevencoes_count",
    Category.PATTERNS: "patterns_count",
    Category.DECISIONS: "decisions_count",
    Category.GLOSSARY: "glossary_count",
}


def _normalize_snippet(*, snippet: str) -> str:
    return _WHITESPACE_RE.sub(" ", snippet.strip().lower())


def _snippet_hash(*, snippet: str) -> str:
    normalized = _normalize_snippet(snippet=snippet)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _source_ref_for(*, item_type: str, item: dict) -> str:
    if item_type == "pull":
        number = item.get("number")
        return f"pull#{number}"
    if item_type == "issue":
        number = item.get("number")
        return f"issue#{number}"
    if item_type == "commit":
        sha = item.get("sha") or ""
        return f"commit:{sha[:12]}"
    if item_type == "review_comment":
        pr_number = item.get("pr_number")
        comment_id = item.get("id")
        return f"review_comment#{comment_id}@pull#{pr_number}"
    if item_type == "issue_comment":
        ref_number = item.get("issue_or_pr_number")
        comment_id = item.get("id")
        return f"issue_comment#{comment_id}@#{ref_number}"
    return f"{item_type}:unknown"


def classify_item(*, item: dict, item_type: str) -> list[ClassifiedItem]:
    if item_type not in _ITEM_TYPES:
        return []
    source_ref = _source_ref_for(item_type=item_type, item=item)
    items: list[ClassifiedItem] = []
    if item_type == "pull":
        title = item.get("title") or ""
        body = item.get("body")
        labels = item.get("labels") or []
        items.extend(classify_conventional(title=title, source_ref=source_ref))
        items.extend(classify_review_cues(body=body, source_ref=source_ref))
        items.extend(classify_labels(labels=labels, source_ref=source_ref, title=title))
        items.extend(classify_adr(title=title, body=body, source_ref=source_ref))
    elif item_type == "issue":
        title = item.get("title") or ""
        body = item.get("body")
        labels = item.get("labels") or []
        items.extend(classify_review_cues(body=body, source_ref=source_ref))
        items.extend(classify_labels(labels=labels, source_ref=source_ref, title=title))
        items.extend(classify_adr(title=title, body=body, source_ref=source_ref))
    elif item_type == "commit":
        message = item.get("message") or ""
        first_line = message.splitlines()[0] if message else ""
        items.extend(classify_conventional(title=first_line, source_ref=source_ref))
        items.extend(classify_review_cues(body=message, source_ref=source_ref))
    elif item_type == "review_comment":
        body = item.get("body")
        items.extend(classify_review_cues(body=body, source_ref=source_ref))
    elif item_type == "issue_comment":
        body = item.get("body")
        items.extend(classify_review_cues(body=body, source_ref=source_ref))
    return items


def mine_glossary(*, settings: Settings, repo: RepoRef) -> list[ClassifiedItem]:
    cache_dir = repo_cache_dir(settings=settings, repo=repo)
    counter: Counter[str] = Counter()
    for filename in ("pulls.jsonl", "issues.jsonl"):
        path = cache_dir / filename
        rows = read_jsonl(path)
        for row in rows:
            title = row.get("title") or ""
            for match in _BACKTICK_RE.finditer(title):
                term = match.group(1).strip()
                if term:
                    counter[term] += 1
            for match in _CAPITALIZED_PHRASE_RE.finditer(title):
                term = match.group(0).strip()
                if term:
                    counter[term] += 1
            labels = row.get("labels") or []
            for raw_label in labels:
                if not raw_label:
                    continue
                label_str = str(raw_label).strip()
                if not label_str:
                    continue
                for match in _BACKTICK_RE.finditer(label_str):
                    term = match.group(1).strip()
                    if term:
                        counter[term] += 1
                for match in _CAPITALIZED_PHRASE_RE.finditer(label_str):
                    term = match.group(0).strip()
                    if term:
                        counter[term] += 1
    items: list[ClassifiedItem] = []
    seen_hashes: set[str] = set()
    for term, count in counter.items():
        if count < _GLOSSARY_FREQUENCY_THRESHOLD:
            continue
        digest = _snippet_hash(snippet=term)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        items.append(
            ClassifiedItem(
                category=Category.GLOSSARY,
                source_ref=_GLOSSARY_SOURCE_REF,
                snippet=term,
                weight=count,
                signals=["glossary:freq"],
            )
        )
    return items


def _bucket_dedupe(
    *,
    bucket: list[ClassifiedItem],
) -> tuple[list[ClassifiedItem], int]:
    seen: dict[str, ClassifiedItem] = {}
    dropped = 0
    for item in bucket:
        digest = _snippet_hash(snippet=item.snippet)
        if digest in seen:
            dropped += 1
            continue
        seen[digest] = item
    return (list(seen.values()), dropped)


def _apply_top_k(
    *,
    bucket: list[ClassifiedItem],
    top_k: int,
) -> tuple[list[ClassifiedItem], int]:
    if len(bucket) <= top_k:
        return (bucket, 0)
    sorted_items = sorted(bucket, key=lambda it: it.weight, reverse=True)
    kept = sorted_items[:top_k]
    dropped = len(bucket) - top_k
    return (kept, dropped)


def _write_bucket(*, out_dir: Path, category: Category, items: list[ClassifiedItem]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{category.value}.jsonl"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")
    os.replace(tmp_path, path)


def _process_resource(
    *,
    cache_dir: Path,
    item_type: str,
    buckets: dict[Category, list[ClassifiedItem]],
) -> tuple[int, int]:
    filename = _RESOURCE_FILENAMES[item_type]
    path = cache_dir / filename
    rows = read_jsonl(path)
    processed = 0
    classified_total = 0
    for row in rows:
        processed += 1
        produced = classify_item(item=row, item_type=item_type)
        for prod in produced:
            buckets[prod.category].append(prod)
            classified_total += 1
    return (processed, classified_total)


def classify(
    *,
    settings: Settings,
    repo: RepoRef,
    top_k: int | None = None,
) -> Result[ClassifyStats]:
    effective_top_k = top_k if top_k is not None else settings.top_k_per_category
    try:
        cache_dir = repo_cache_dir(settings=settings, repo=repo)
        buckets: dict[Category, list[ClassifiedItem]] = {cat: [] for cat in Category}

        total_processed = 0
        total_classified = 0
        for item_type in _ITEM_TYPES:
            processed, classified_count = _process_resource(
                cache_dir=cache_dir,
                item_type=item_type,
                buckets=buckets,
            )
            total_processed += processed
            total_classified += classified_count

        glossary_items = mine_glossary(settings=settings, repo=repo)
        for gloss_item in glossary_items:
            buckets[Category.GLOSSARY].append(gloss_item)
            total_classified += 1

        dropped_dupes_total = 0
        dropped_top_k_total = 0
        deduped_buckets: dict[Category, list[ClassifiedItem]] = {}
        for category, bucket in buckets.items():
            deduped, dropped_dupes = _bucket_dedupe(bucket=bucket)
            dropped_dupes_total += dropped_dupes
            capped, dropped_top_k = _apply_top_k(bucket=deduped, top_k=effective_top_k)
            dropped_top_k_total += dropped_top_k
            deduped_buckets[category] = capped

        out_dir = cache_dir / "classified"
        for category, items in deduped_buckets.items():
            _write_bucket(out_dir=out_dir, category=category, items=items)
            console.print(f"[green]✓[/green] Wrote {len(items)} items to {category.value}.jsonl")

        stats = ClassifyStats(
            rules_count=len(deduped_buckets[Category.RULES]),
            prevencoes_count=len(deduped_buckets[Category.PREVENCOES]),
            patterns_count=len(deduped_buckets[Category.PATTERNS]),
            decisions_count=len(deduped_buckets[Category.DECISIONS]),
            glossary_count=len(deduped_buckets[Category.GLOSSARY]),
            total_items_processed=total_processed,
            total_classified=total_classified,
            dropped_dupes=dropped_dupes_total,
            dropped_top_k=dropped_top_k_total,
        )
        return Result[ClassifyStats](success=True, data=stats)
    except Exception as exc:
        logger.exception("Classify failed")
        return Result[ClassifyStats](
            success=False,
            error_code="CLASSIFY_FAILED",
            error_message=str(exc),
        )
