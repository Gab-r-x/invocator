# invocator — Engineering Standards

Non-negotiable rules for the `invocator` codebase. Adapted from a stricter backend ruleset to the realities of this project: a Typer CLI that wraps the `gh` subprocess, caches GitHub data to JSONL on disk, and calls the Anthropic API to synthesize markdown.

## Table of Contents

1. [Type Safety on I/O Boundaries](#1-type-safety-on-io-boundaries)
2. [Keyword-Only Method Signatures](#2-keyword-only-method-signatures)
3. [Error Handling with `Result[T]`](#3-error-handling-with-resultt)
4. [Units in Attribute Names](#4-units-in-attribute-names)
5. [Nullability Has Meaning](#5-nullability-has-meaning)
6. [Enums for Status & State Machines](#6-enums-for-status--state-machines)
7. [Try/Catch is Not Logic](#7-trycatch-is-not-logic)
8. [Clean Code Doesn't Need Comments](#8-clean-code-doesnt-need-comments)
9. [No Dynamic Attribute Access](#9-no-dynamic-attribute-access)
10. [Imports at Top of File](#10-imports-at-top-of-file)
11. [Logging via Rich Console](#11-logging-via-rich-console)
12. [Type Safety with Generics](#12-type-safety-with-generics)
13. [CLI Rule: No Bare `print()`](#13-cli-rule-no-bare-print)
14. [LLM Rule: Explicit Prompt Caching & Cost Awareness](#14-llm-rule-explicit-prompt-caching--cost-awareness)
15. [gh Rule: No Direct GitHub HTTP](#15-gh-rule-no-direct-github-http)
16. [Cache Rule: Append-Only JSONL + Watermark](#16-cache-rule-append-only-jsonl--watermark)

---

## 1. Type Safety on I/O Boundaries

Use Pydantic at boundaries where contracts matter; explicit parameters internally.

**Pydantic required for:**
- Parsing raw GitHub JSON returned by `gh api` (`PR`, `Issue`, `Commit`, `ReviewComment`)
- Anthropic request/response messages
- Config files (`~/.invocator/config.toml` parsed via Pydantic)
- Any object that flows through 3+ internal functions

**Explicit parameters for** single-use internal functions (1-2 callers).

**Never** return raw `dict`/`list` for structured data. **Never** return `Any` unless it crosses an untyped external boundary.

```python
# Good
class PullRequest(BaseModel):
    number: int
    title: str
    body: str | None = None
    labels: list[str] = Field(default_factory=list)
    merged_at_utc: datetime | None = None

async def parse_pulls(*, raw_json: bytes) -> list[PullRequest]:
    ...
```

---

## 2. Keyword-Only Method Signatures

All function parameters (except `self`/`cls`) MUST be keyword-only via `*`.

```python
async def synthesize_category(
    *,
    category: Category,
    classified_items: list[ClassifiedItem],
    model: str,
) -> Result[str]:
    ...
```

**Exception:** Typer command functions are exempt — Typer binds positional args, options, and arguments automatically.

```python
# app.command() — no `*` needed
@app.command("cost")
def scry_cost(repo: str, since: str | None = None) -> None:
    ...
```

Internal helpers called by command functions still require `*`.

**Exception:** Dunder methods (`__init__`, etc.) can use positional args.

---

## 3. Error Handling with `Result[T]`

Use `Result[T]` for **expected** errors. Let unexpected exceptions bubble to the CLI top-level handler in `cli.py`, which logs the traceback and exits with code 1.

**Use `Result[T]` for:**
- gh subprocess non-zero exits (`gh not installed`, `not authenticated`, repo 404)
- Anthropic API errors (rate limit, overload, auth)
- Cache I/O errors (corrupt JSONL, missing watermark)
- Validation failures (invalid `--repo` format)

**Let exceptions bubble for:**
- Programming bugs (`KeyError`, `AttributeError`)
- Truly infrastructural (disk full, OOM)

`Result` lives in [src/invocator/result.py](../src/invocator/result.py); same shape as the reference: `success`, `data`, `error_message`, `error_context`, `error_code`, `error_grouping_prefix`. Top-level command functions translate `Result.error_code` into exit codes + Rich error panels.

---

## 4. Units in Attribute Names

```python
# Good
created_at_utc: datetime
cache_ttl_seconds: int
file_size_bytes: int
estimated_cost_usd_cents: int     # store $2.34 as 234
prompt_tokens: int
completion_tokens: int

# Bad
created_at: datetime       # timezone ambiguous
size: int                  # bytes? KB?
cost: float                # currency? floating-point money
```

All datetimes UTC-aware: `datetime.now(timezone.utc)`. Never `datetime.now()` bare.

---

## 5. Nullability Has Meaning

`None` = unknown / not applicable. Empty string / 0 / empty list are real values, not sentinels.

```python
pr.merged_at_utc = None     # not merged
pr.merged_at_utc = datetime(...)   # merged at that time

classified.signals = []     # classified, no signals fired
classified.signals = None   # NEVER — meaningless ambiguity
```

Required fields: never `None`. Optional fields: `T | None = None` explicit.

---

## 6. Enums for Status & State Machines

```python
class Category(str, Enum):
    RULES = "rules"
    PREVENCOES = "prevencoes"
    PATTERNS = "patterns"
    DECISIONS = "decisions"
    GLOSSARY = "glossary"

class SynthesisStatus(str, Enum):
    PENDING = "pending"
    CACHED = "cached"          # hash matched, LLM skipped
    SYNTHESIZED = "synthesized"
    FAILED = "failed"
```

Never raw strings for categorical fields. Query/compare with `.value` when serializing to JSONL.

---

## 7. Try/Catch is Not Logic

```python
# Bad
try:
    pr = parsed_prs[0]
except IndexError:
    pr = None

# Good
pr = parsed_prs[0] if parsed_prs else None

# Bad
try:
    value = config["api_key"]
except KeyError:
    value = None

# Good
value = config.get("api_key")
```

`try/except` only for genuine exceptional paths: subprocess failures, network errors, file I/O. Never for control flow.

---

## 8. Clean Code Doesn't Need Comments

Default: no comments. Add only when the **why** is non-obvious.

```python
# Good — explains a hidden constraint
# UUIDv7 prefix sorts lexicographically by creation time; do not switch to uuid4
# without re-evaluating cache merge order.

# Good — references an external invariant
# GitHub's pulls/comments endpoint is repo-wide and ALREADY paginates all
# review comments across all PRs; do not loop per-PR.

# Bad — explains the what
# Get the user's email
email = user.email
```

Never comment out code — delete it; git keeps history.

---

## 9. No Dynamic Attribute Access

No `getattr`, `hasattr`, `setattr` on objects we control.

```python
# Bad
for field in ["title", "body", "labels"]:
    value = getattr(pr, field)

# Good
print(pr.title, pr.body, pr.labels)
```

Allowed only for genuinely external dynamic data (e.g. webhook payloads with unknown keys), and even then prefer parsing into a typed model first.

---

## 10. Imports at Top of File

PEP 8 order: stdlib → third-party → local. Blank line between groups.

```python
import logging
from pathlib import Path

from anthropic import Anthropic
from pydantic import BaseModel, Field

from invocator.result import Result
from invocator.models import PullRequest
```

No lazy imports inside functions. Circular import → refactor or use `TYPE_CHECKING`.

---

## 11. Logging via Rich Console

Use `rich.console.Console` for user-facing output. Use `logging` for diagnostics that respect `--verbose`.

```python
from rich.console import Console

console = Console()
err_console = Console(stderr=True)

console.print(f"[green]✓[/green] Cached {count} PRs")
err_console.print(f"[red]✗[/red] gh not authenticated")
```

Error logs include: relevant IDs (`repo`, `pr_number`, `category`), the error itself, traceback when caught. Level matches severity — caught exception that signals failure → `logger.error`, never `debug`.

---

## 12. Type Safety with Generics

`Result[T]`, `Cache[T]`, etc. must preserve their type parameter through chains.

```python
T = TypeVar("T")

class Result(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    ...

# Good
async def fetch_pulls(*, repo: str) -> Result[list[PullRequest]]:
    ...

# Bad — caller now has Result[Any]
async def fetch_pulls(*, repo: str) -> Result:
    ...
```

Run `pyright src/` in CI. If IntelliSense can't resolve a method on a generic, the type is erased somewhere.

---

## 13. CLI Rule: No Bare `print()`

All user-facing output goes through `rich.console.Console`. This ensures:
- `--quiet` / `--verbose` honored
- Color/markup uniform
- Stderr vs stdout intentional (status to stderr, data to stdout for pipeability)

```python
# Bad
print("Done")

# Good
console.print("[green]✓[/green] Done")
```

Exception: `--json` output mode for `scry cost` prints raw JSON to stdout via `print(json.dumps(...))` for machine consumption.

---

## 14. LLM Rule: Explicit Prompt Caching & Cost Awareness

Every Anthropic call must:

1. **Use prompt caching explicitly** on stable blocks: `{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}` for the system prompt and the corpus bundle.
2. **Estimate tokens before sending.** Use `anthropic.Anthropic().messages.count_tokens(...)` or local approximation; refuse to send if estimated > soft cap (default 200k input) without explicit `--force`.
3. **Log usage** from the response: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, and computed USD cost.

```python
response = client.messages.create(
    model=settings.model,
    max_tokens=8000,
    temperature=0,
    system=[
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ],
    messages=[...],
)
log_usage(response=response, category=category)
```

Synthesis cache: SHA1 of corpus bundle → `learnings/.cache/<category>.hash`. Hash match = skip LLM entirely.

---

## 15. gh Rule: No Direct GitHub HTTP

Never `import httpx` / `import requests` to hit `api.github.com`. Always go through `gh api` subprocess via [src/invocator/gh_client.py](../src/invocator/gh_client.py). Reasons:

- Inherits the user's `gh auth login` token (no env var plumbing)
- `gh` handles secondary rate limits with retry
- `gh api --paginate` handles Link-header pagination
- Works with GitHub Enterprise via `gh auth login --hostname`

```python
# Good
raw = await run_gh(["api", "--paginate", f"repos/{repo}/pulls?state=all"])

# Bad
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.github.com/repos/...")
```

---

## 16. Cache Rule: Append-Only JSONL + Watermark

Cache directory layout: see [docs/todos/README.md](todos/README.md) and the main plan. Rules:

- One JSONL file per resource. New items **appended**; updated items **merged by `id`** via rewrite-on-merge (full file rewrite acceptable here because merge frequency is low).
- Watermark stored as ISO8601 in `watermark.json`, **per resource**. Updated only on successful completion of that resource's fetch.
- Never mutate a row in place mid-file. Never partial-write — write to `.tmp` then `os.replace()`.
- Classified items are derived; their JSONL can be regenerated from raw cache + heuristics deterministically.

---

## Code Review Checklist

Before submitting code, verify:

- [ ] Pydantic models on all I/O boundaries (gh JSON, Anthropic, config files)
- [ ] No raw dict/list returns for structured data
- [ ] All internal methods use keyword-only args (`*`); Typer commands exempt
- [ ] `Result[T]` for expected errors; exceptions bubble for bugs
- [ ] Units in attribute names (`_utc`, `_seconds`, `_bytes`, `_usd_cents`, `_tokens`)
- [ ] Nullability explicit; no sentinel `""`/`0`/`[]` for "missing"
- [ ] Status fields are Enums
- [ ] No `try/except` for control flow
- [ ] Comments explain why, not what
- [ ] No `getattr`/`hasattr`/`setattr` on owned objects
- [ ] Imports at top of file
- [ ] User output via `rich.console.Console`; no bare `print()` except `--json` mode
- [ ] Anthropic calls use prompt caching + log usage
- [ ] No direct `api.github.com` HTTP — all via `gh` subprocess
- [ ] JSONL cache append-only with watermark per resource
- [ ] `Result[T]` and other generics carry their type parameter through the chain

---

## Enforcement

```bash
black --check --line-length=100 src/ tests/
isort --check-only --profile=black src/ tests/
flake8 --max-line-length=100 src/ tests/
pyright src/
pytest tests/ -v
```

Every command exits 0 before a phase is declared done. CI runs the same set.
