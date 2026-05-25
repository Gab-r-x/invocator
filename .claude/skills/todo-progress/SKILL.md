---
name: todo-progress
description: Syncs a docs/todos/todo_<feature>.md file with the actual state of src/invocator/. Marks completed items [x] and writes/updates an "Implementation Notes" block per phase that todo-tests consumes. Use after implementing a phase or when the todo drifts from code.
---

# /todo-progress — Todo synchronizer

Use this skill to update [docs/todos/todo_<feature>.md](../../../docs/todos/) after implementing a phase, or when the todo is out of sync with the code in `src/invocator/`. This skill only edits the todo file. It never edits `src/` and never writes tests.

## Arguments

- `<feature>` (required) — todo slug.
- `<phase>` (optional) — phase number or name. If omitted, sweep every phase.

## Prerequisites (always read before starting)

1. [docs/todos/todo_<feature>.md](../../../docs/todos/) — the full plan; single source of truth for what must exist.
2. [docs/STANDARDS.md](../../../docs/STANDARDS.md) — conventions that constrain implementation shape (so you can recognize a real implementation vs a stub).
3. Entry points and recent changes in `src/invocator/`:
   - [src/invocator/cli.py](../../../src/invocator/cli.py) — Typer app; what spells are wired.
   - [src/invocator/commands/](../../../src/invocator/commands/) — one file per spell group (`extract.py`, `forge.py`, `scry.py`).
   - [src/invocator/__init__.py](../../../src/invocator/__init__.py) — what's exported.
   - `git log -p --since="1 week"` — recent diffs that may correspond to phase items.
4. [pyproject.toml](../../../pyproject.toml) — installed deps reveal what infrastructure is in place.

For a thorough sweep, dispatch an `Explore` subagent to map sub-items to source files. The orchestrator's context stays cheap; the subagent returns a phase → file mapping.

## Procedure (per phase)

### 1. Map the phase to the code

**Read prior phases' `### Implementation Notes` first.** The `**Files:**` line is an authoritative pointer to where related code lives. Open those files before searching elsewhere — most of the time you don't need to grep at all. Only fall back to `Grep`/`Glob`/Explore when the notes are missing, the file path is stale (renamed/moved), or the item references something genuinely new.

Order of operations:
1. Read `**Files:**` from the current phase's notes (if any) and from prior phases.
2. `Read` those files directly to confirm the implementation.
3. Only if step 2 doesn't account for a sub-item, `Grep` for the symbol/string in `src/`.

Mapping examples (when starting fresh and no prior notes exist):
- "forge key command" → [src/invocator/commands/forge.py](../../../src/invocator/commands/forge.py)
- "gh subprocess wrapper" → [src/invocator/gh_client.py](../../../src/invocator/gh_client.py), look for `run_gh`, `check_gh_installed`, `check_auth`
- "scry cost probe" → [src/invocator/commands/scry.py](../../../src/invocator/commands/scry.py), check for Link-header parsing
- "JSONL cache" → [src/invocator/cache.py](../../../src/invocator/cache.py), look for `append_jsonl`, `merge_by_id`, `load_watermark`
- "classify rules" → [src/invocator/classify.py](../../../src/invocator/classify.py) + [src/invocator/rules/](../../../src/invocator/rules/)
- "prompt caching" → [src/invocator/synthesize.py](../../../src/invocator/synthesize.py), verify `cache_control={"type": "ephemeral"}` is present on system + corpus blocks
- "synthesis cache" → check `learnings/.cache/<category>.hash` write path

### 2. Update checkboxes

- `[ ]` → `[x]` **only** when there is code that implements the item, not a stub or `# TODO` comment. A file containing only `pass` or `__all__ = []` is a stub.
- Partially done → `[~]`, with the gap recorded in Implementation Notes.
- Never mark `[x]` based on intent or on another `[x]` — the evidence is the code.
- A phase header gets `[x]` only when **every** sub-item is `[x]`.

### 3. Add/update "Implementation Notes"

Immediately below the last sub-item of the phase (before the `---` separator), ensure there is a block in **exactly** this format:

```markdown
### Implementation Notes

- **Files:** `src/invocator/commands/scry.py`, `src/invocator/gh_client.py:88`, ...
- **Public entry points:** `invocator scry cost`, `gh_client.run_gh(...)`, `gh_client.estimate_items(...)`
- **Key behaviors / invariants:**
  - <behavior 1 a test must know about>
  - <behavior 2>
- **Edge cases observed in code:**
  - <e.g. Link header `rel="last"` absent → infer single page from response body length>
  - <e.g. `gh auth status` non-zero → return Result with error_code=GH_NOT_AUTHENTICATED, not raise>
- **Cache / file layout:**
  - <e.g. `~/.invocator/config.toml` chmod 600 on write>
  - <e.g. watermark.json updated per resource only on full successful paginated fetch>
- **Result[T] usage:**
  - <which methods return Result, which raise; which error_codes are emitted>
- **LLM / cost details (if relevant):**
  - <e.g. system prompt cached via ephemeral; corpus block cached; usage logged via log_usage()>
- **Not yet implemented (referenced by todo):**
  - <items still `[ ]` and why>
- **Test hooks / seams:**
  - <e.g. `gh_client.run_gh` is a module-level function — patch via `monkeypatch.setattr("invocator.gh_client.run_gh", fake)` returning fixture bytes>
  - <e.g. `anthropic.Anthropic` instantiated lazily in `synthesize._get_client()` — patch that factory>
```

Rules:
- Write in **English** (consistency across all docs).
- **Keep it lean.** The `**Files:**` line is the index — list every file the phase touched (with `:line` when a specific symbol matters), comma-separated, one line. Downstream skills (`todo-tests`, future `todo-progress` runs) read that line first to avoid re-grepping the codebase, so it must be complete and current.
- Be specific: cite files, methods, line numbers when they add value. Never generic ("handles requests").
- Describe what the **code** does, not what the todo said it should do — record divergences explicitly.
- If a phase is 100% not implemented, still create the block with only `Not yet implemented:` filled. Signals to `todo-tests` that there's nothing to test yet.
- If a block already exists, **update** it; do not duplicate.
- Do not touch the `### Tests` block (owned by `todo-tests`).

### 4. Verification

Before finishing:
- Re-read the diff to `docs/todos/todo_<feature>.md`.
- Confirm every `[x]` has a code counterpart (quick `Grep` or `Read`).
- Confirm every "Edge case" / "Key behavior" is verifiable from code, not invented.
- Run `pyright src/` — a phase that doesn't typecheck is not complete regardless of checkboxes.

## Output to user (≤6 lines)

- Phases processed.
- Items marked `[x]` (count or short list).
- Phases with no implementation yet.
- Code ↔ todo divergences found and how each was resolved (notes only, or escalated).

## What NOT to do

- Do not write tests — that's `todo-tests`.
- Do not edit `src/` or `tests/`. This skill edits only the todo file.
- Do not add new sub-items to the todo unless the user explicitly asks. Record observations in "Implementation Notes" instead.
- Do not mark a phase header `[x]` unless every sub-item is `[x]`.
- Do not `git commit` — the user decides.
