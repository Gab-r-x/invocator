---
name: todo-orchestrator
description: Drives a phased todo file under docs/todos/ from start to finish, dispatching the todo-executor → todo-progress → todo-tests cycle phase by phase via subagents. Use when the user wants to ship a feature whose checklist already exists in docs/todos/todo_<feature>.md.
---

# /todo-orchestrator — Phase-by-phase feature driver

Use this skill to drive a feature from a written todo to "phases all `[x]`, tests green". The orchestrator reads the todo, picks the next pending phase, and dispatches three subagents in sequence (executor, progress, tests) before moving to the next phase.

## Arguments

- `<feature>` (required) — the feature slug, e.g. `scaffold`. Resolves to [docs/todos/todo_<feature>.md](../../../docs/todos/).
- `<phase>` (optional) — phase number or name. If omitted, the orchestrator processes the lowest-numbered phase with any `[ ]` items, then continues until the user stops it or all phases are `[x]`.

If `<feature>` is omitted, list candidate files under `docs/todos/` and ask the user which one.

## Prerequisites (read once at start)

1. [docs/todos/README.md](../../../docs/todos/README.md) — operational contract (file structure, lifecycle, gates).
2. [docs/todos/todo_<feature>.md](../../../docs/todos/) — the target todo. Identify pending phases.
3. [docs/STANDARDS.md](../../../docs/STANDARDS.md) — non-negotiable rules. Subagents must follow these.
4. [CLAUDE.md](../../../CLAUDE.md) if present — project workflow (branching, commits, planning).

Do **not** read the entire `src/` tree from the orchestrator. That's what subagents are for — keep your context window cheap.

## Procedure

### 1. Pick the next phase

Read the todo file. Identify the lowest-numbered phase with at least one `[ ]` sub-item. If `<phase>` was provided, use that one.

### 2. Dispatch executor subagent

Spawn an `Agent` (subagent_type `general-purpose`) with a prompt that:
- Names the target file (`docs/todos/todo_<feature>.md`) and target phase.
- **Quotes the `**Files:**` line from each prior phase's `### Implementation Notes`** (read them yourself once before dispatch). The subagent uses these as its starting reads — it should `Read` those files directly before any `Grep`/`Glob`. Saves an entire context window of codebase exploration.
- Tells it to invoke the `todo-executor` skill behavior (you can either reference the skill file path or inline the executor's procedure if the subagent can't load skills).
- Reminds it of the hard rules: don't mark `[x]`, don't write tests, don't commit, follow STANDARDS.

Wait for the subagent to return. Read its summary. **Verify** by running locally:
- `git status` to see what changed.
- `black --check --line-length=100 src/`, `pyright src/` — implementation phase isn't done if these don't pass.

If the executor returned with errors or skipped items, decide: re-dispatch with a corrective prompt, escalate to the user, or move on with the gap recorded.

### 3. Dispatch progress subagent

Spawn a fresh `Agent` (general-purpose) to invoke `todo-progress` for the same phase. Its job is to:
- Cross-check `[ ]` items against the actual code in `src/`.
- Flip `[ ]` → `[x]` (or `[~]`) **only** where code exists.
- Append/update the `### Implementation Notes` block.

Verify the diff: only `docs/todos/todo_<feature>.md` should be modified.

### 4. Dispatch tests subagent

Spawn a fresh `Agent` (general-purpose) to invoke `todo-tests` for the same phase. Its job is to:
- Plan the `### Tests` checklist from the Implementation Notes.
- Write CLI integration tests under `tests/` mirroring `src/invocator/`.
- Run `pytest tests/ -v` and report pass/fail.

If tests fail, do **not** silently fix them by editing tests. Either re-dispatch executor with the failure context, or escalate to the user.

### 5. Run verification gates

After tests pass, run from the orchestrator (not a subagent — these are fast, in-context):

```bash
black --check --line-length=100 src/ tests/
isort --check-only --profile=black src/ tests/
flake8 --max-line-length=100 src/ tests/
pyright src/
pytest tests/ -v
```

If the phase touched runtime CLI behavior, also smoke-test:
```bash
pip install -e . --quiet
invocator --help        # confirms the entrypoint resolves
# plus any spell the phase added, with --help or a --dry-run path that exercises no network
```

Every command must exit 0 before declaring the phase done. If any fail, fix in a follow-up dispatch and re-run.

### 6. Loop or stop

- If the user gave an explicit `<phase>`, stop after that phase.
- Otherwise, loop back to step 1. Stop automatically when no `[ ]` remain.
- After the **last** phase completes, move the file: `mkdir -p docs/past/$(date +%Y-%m) && mv docs/todos/todo_<feature>.md docs/past/$(date +%Y-%m)/`. Tell the user the feature is shipped.

## Subagent dispatch — concrete shape

When sub-items in a phase are independent (e.g. unrelated modules under `src/invocator/`), the executor subagent itself can fan out to additional general-purpose agents in parallel. The orchestrator does not need to manage that — just give the executor permission to parallelize when it makes sense.

**One message, multiple `Agent` calls** is required when launching parallel subagents. Sequential dispatch (executor → progress → tests) must be one-at-a-time because each step depends on the previous.

## Output to user

Report at phase boundaries (not per sub-item) in ≤8 lines:
- Phase N name + status (✓ done, ⚠ partial, ✗ blocked).
- Files created/modified (counts).
- Test results: pass/fail counts.
- Lint/typecheck: ✓ or the failing command.
- What runs next (next phase, or "feature shipped — todo moved to docs/past/").

## What NOT to do

- **Never** edit `src/`, `tests/`, or the todo file directly from the orchestrator. All writes happen inside subagents. The orchestrator only reads, runs gate commands, and dispatches.
- **Never** mark a phase `[x]` yourself — that's `todo-progress`'s contract.
- **Never** commit. The user commits when they decide.
- **Never** skip a verification gate "just this once". A green pyright is the difference between shipped and rolled-back.
- **Never** read the entire codebase to "understand context" — that's what subagents do in their own windows.
