---
name: todo-executor
description: Implements one phase of a todo file under docs/todos/. Writes code in src/invocator/. Does NOT mark checkboxes (todo-progress) and does NOT write tests (todo-tests). Use when a phase has pending [ ] items and you want them implemented.
---

# /todo-executor — Phase implementer driven by docs/todos/

Use this skill to implement a single phase of [docs/todos/todo_<feature>.md](../../../docs/todos/). It writes code in `src/invocator/`. It does **not** update checkboxes (that's `todo-progress`) and does **not** write tests (that's `todo-tests`). Keeping these three responsibilities separate is what makes the pipeline safe across multiple sessions.

## Arguments

- `<feature>` (required) — todo slug. Resolves to [docs/todos/todo_<feature>.md](../../../docs/todos/).
- `<phase>` (optional) — phase number or name. If omitted, target the lowest-numbered phase with any `[ ]` items.

## Prerequisites (always read before starting)

1. [docs/todos/todo_<feature>.md](../../../docs/todos/) — find the target phase. Read every sub-item.
2. [docs/STANDARDS.md](../../../docs/STANDARDS.md) — the 16 rules are hard constraints. Re-read sections 2 (keyword-only `*`), 3 (`Result[T]`), 6 (enums), 12 (generics), 13 (no bare print), 14 (LLM caching), 15 (gh subprocess only), 16 (JSONL cache).
3. [CLAUDE.md](../../../CLAUDE.md) if present — workflow, branch convention.
4. `### Implementation Notes` of **all prior phases** in the same todo — they describe what's already in place. Ignoring them duplicates or breaks existing code. **The `**Files:**` line is your entry point**: open those files directly via `Read` before doing any `Grep`/`Glob` against the codebase. Only fall back to a wider search if the notes are missing or the path is stale.
5. [src/invocator/](../../../src/invocator/) — current source tree. Touch only what the phase requires.
6. [pyproject.toml](../../../pyproject.toml) — installed dependencies. If a dependency is missing, add it; do not bring in extras.

## Procedure

### 1. Scope the work

- Parse the phase's sub-items. Build a checklist of files that must exist or change.
- Identify cross-phase dependencies: if this phase needs something from a `[ ]` item in an earlier phase, **stop** and tell the user — the todo is out of order or an earlier phase is incomplete.
- If the phase has an existing `### Implementation Notes` block (partial prior run), treat your job as **filling the gaps**, not rewriting. Respect existing decisions.

### 2. Implement, small steps

Implement one sub-item at a time. Per sub-item:
- Touch only the files the sub-item requires.
- After every 2–3 sub-items, run `pyright src/` and `python3 -m py_compile <touched files>`. Fix errors immediately. Do not accumulate broken code.
- Follow STANDARDS rigidly: keyword-only args (`*`), `Result[T]` for expected errors, Pydantic on boundaries, enums for status fields, no `getattr/setattr/hasattr`, no bare `print()`, no direct `api.github.com` HTTP (`gh` subprocess only), explicit prompt caching on every Anthropic call, JSONL cache append-only with watermark.

### 3. Parallelize when safe

If sub-items are independent (different files, no shared state), dispatch them to general-purpose subagents **in parallel** (one message, multiple `Agent` calls). Examples that parallelize well:
- An unrelated heuristic rule module and an unrelated cache utility.
- The prompts module and a Typer command stub it doesn't depend on yet.

Examples that **must** run sequentially:
- A new pydantic model and the parser that imports it.
- A `Result[T]` refactor and the callers that consume it.

When in doubt, run sequentially. The cost of serial work is wall-clock; the cost of a race is a broken commit.

### 4. Verify at the phase boundary

When every sub-item is implemented, all of these must pass before reporting done:

```bash
black --check --line-length=100 src/ tests/
isort --check-only --profile=black src/ tests/
flake8 --max-line-length=100 src/ tests/
pyright src/
```

If the phase touched the CLI entrypoint or added a spell, also:
```bash
pip install -e . --quiet
invocator --help                           # confirm entrypoint resolves
invocator <new-spell> --help               # confirm subcommand wired
# if the spell has a no-network path, exercise it
invocator scry cost --repo owner/name --dry-run  # for example
```

Lint/format failures: run the formatter (`black src/ tests/`, `isort src/ tests/`) and re-check. Don't disable rules.

### 5. Report — do NOT update checkboxes

This skill **never** marks `[x]` in the todo. That's `todo-progress`'s job, which cross-checks claims against code.

## Output to user (≤10 lines)

- Phase number and name.
- Files: created (list), modified (list).
- Sub-items skipped/deferred and why.
- Deviations from the todo (renamed file, split module) and why.
- Lint/typecheck status: ✓ or the failing command.
- Next: "Run `/todo-progress <feature> <phase>` then `/todo-tests <feature> <phase>`."

## What NOT to do

- **Never** mark items `[x]` in the todo. That contract belongs to `todo-progress`.
- **Never** write tests under `tests/`. That belongs to `todo-tests`.
- **Never** implement more than the target phase. The phased structure exists so progress and tests lock in work before the surface grows.
- **Never** skip prior phases' Implementation Notes. Skipping them duplicates or breaks integrations.
- **Never** `git commit`. The user commits.
- **Never** install dependencies the phase does not require. If a missing one is needed, stop and ask.
- **Never** put secrets (Anthropic API key, GitHub tokens) in code, logs, or error messages. Mask them in any user-facing display.
- **Never** bypass `Result[T]` for expected errors or use `try/catch` for control flow (STANDARDS Rule 7).
- **Never** call `api.github.com` directly with `httpx`/`requests`. Use `gh api` subprocess (STANDARDS Rule 15).
- **Never** send an Anthropic request without explicit `cache_control` on stable blocks and without logging usage (STANDARDS Rule 14).
