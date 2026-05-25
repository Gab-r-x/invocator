---
name: todo-tests
description: For each phase of docs/todos/todo_<feature>.md, plans the test checklist (inside the todo) and writes pytest tests under tests/ mirroring src/invocator/. Consumes the Implementation Notes block written by todo-progress. Use when a phase is implemented and needs coverage.
---

# /todo-tests — Test generator for invocator

Use this skill to (1) plan the test checklist inside the todo and (2) write the pytest tests under `tests/`. Testing convention is **CLI integration**: exercise spells through `typer.testing.CliRunner` against the in-process Typer app, with `gh` subprocess and the Anthropic client mocked. No live network. No real `gh auth`. No real API tokens.

## Arguments

- `<feature>` (required) — todo slug.
- `<phase>` (optional) — phase number or name. If omitted, sweep every phase that has at least one `[x]` and no complete `### Tests` block.

## Prerequisites (always read before starting)

1. [docs/todos/todo_<feature>.md](../../../docs/todos/) — especially each phase's `### Implementation Notes`. **If a phase has no Implementation Notes block, stop and tell the user to run `/todo-progress` first.** Without those notes you'll invent tests that don't map to real code.
2. **`**Files:**` line of the Implementation Notes is the source-of-truth for what to read.** Open those files directly via `Read` — that's the code you're testing. Do **not** `Grep`/`Glob` the codebase searching for the feature: if it isn't in the Files list, either the notes are stale (escalate to `/todo-progress`) or the item isn't implemented yet (don't test it). Only fall back to a wider search when a referenced path 404s or the symbol mentioned in Edge cases / Key behaviors clearly lives elsewhere.
3. [docs/STANDARDS.md](../../../docs/STANDARDS.md) — conventions tests must respect (`Result[T]`, keyword-only args, enums, no bare print, mask secrets, etc.).
4. [tests/](../../../tests/) — existing tests, to avoid duplicating cases or drifting from style.
5. [tests/fixtures/](../../../tests/fixtures/) — frozen `gh api` JSON used as mock returns. Reuse before creating new fixtures.

## Procedure (per phase)

### 1. Plan the tests inside the todo

Immediately below the phase's `### Implementation Notes` block, add (or update) a block in **exactly** this format:

```markdown
### Tests

**Target file(s):** `tests/commands/test_scry.py` (mirror the source file 1:1)

**Cases to cover:**
- [ ] happy: `scry cost --repo owner/name` prints table with item counts from fixture
- [ ] happy: estimate honors `--model sonnet` vs `--model opus` (different $ in output)
- [ ] edge: repo with `Link: ...rel="last"` absent → falls back to 1-page inference
- [ ] edge: `--exclude-bots` flag drops dependabot from the count
- [ ] error: `gh` not installed → exit code 2 + clear stderr message, no traceback
- [ ] error: `gh auth status` non-zero → Result with error_code=GH_NOT_AUTHENTICATED, exit code 2
```

Checklist rules:
- **One case per line.** No grouping ("tests several edge cases").
- Each case maps to an `[x]` item or to an entry in `Edge cases observed in code` / `Key behaviors`. Do not invent tests unanchored from code.
- Prefix with `happy:`, `edge:`, or `error:` so a reader can classify at a glance.
- If a sub-item is `[ ]` (not implemented), **do not** generate a case. Leave a line `<!-- pending: <item> not implemented -->` for traceability.

### 2. Write the tests

For each `[ ]` case, write the test:

- **Target file:** `tests/<same-path-as-source>.py`. Source `src/invocator/commands/scry.py` → `tests/commands/test_scry.py`. Append to existing files; do not rewrite.
- **Framework:** `pytest` + `typer.testing.CliRunner`. Match existing style.

```python
from typer.testing import CliRunner
from invocator.cli import app

runner = CliRunner()

def test_scry_cost_happy(monkeypatch, gh_fixture):
    monkeypatch.setattr(
        "invocator.gh_client.run_gh",
        lambda args, **kw: gh_fixture("pulls_page1.json"),
    )
    result = runner.invoke(app, ["scry", "cost", "--repo", "OleveCo/CourseGPTBackend"])
    assert result.exit_code == 0
    assert "1300 PRs" in result.stdout
```

- **No network. Ever.** Patch `invocator.gh_client.run_gh` with fixture returns. Patch the Anthropic client factory (e.g. `invocator.synthesize._get_client`) with a fake that asserts the request shape and returns a canned response.
- **No real files outside tmp.** Cache writes use a `tmp_path` fixture; config writes use `monkeypatch.setenv("HOME", str(tmp_path))`.
- **Style follows STANDARDS:**
  - Keyword-only args on helpers (`*` after first param).
  - `Result[T]` is the contract for internal calls — assert on `result.success` and `result.error_code`, don't try/catch.
  - Pydantic models for parsed data, not raw dicts in assertions.
  - Enums by name in assertions (e.g. `Category.RULES`), not raw strings.
- **Mocking boundaries:**
  - **`gh` subprocess:** patch `invocator.gh_client.run_gh`. Return fixture bytes loaded from `tests/fixtures/gh_api/`. Verify with `assert_called_with(...)` when args matter.
  - **Anthropic:** patch the client factory. Fake `messages.create` returns a `Message`-shaped object with `usage` populated so cost logging works.
  - **Filesystem (cache, config):** use `tmp_path`; never touch the real `~/.invocator/`.
  - **Time:** use `freezegun.freeze_time` if behavior depends on `datetime.now(timezone.utc)` (e.g. watermark timestamps).
  - **Secrets:** test config writes the API key but assertions on `result.stdout` must never include the unmasked key — if a test ever sees `sk-ant-...` in output, that's a real bug.
- Imports at the top of the file (STANDARDS Rule 10).
- Do not create helpers used only once. Inline unless repeated 3+ times.
- One assertion per intent — long chains hide which assert failed.

After each case is written, mark it `[x]` in the todo's Tests checklist.

### 3. Run and verify

```bash
pytest tests/<path>/test_<file>.py -v
```

Then the full suite:
```bash
pytest tests/ -v
```

- All new tests must pass. Existing tests must still pass.
- If a test fails because the **code** does something different from the notes, **do not "fix" the test to make it pass**. Stop and propose: (a) update notes via `/todo-progress`, (b) fix the code via `/todo-executor`, or (c) adjust the test if you misunderstood.
- If it fails due to infra (missing fixture, conftest issue, mocked dep changed), tell the user the exact change needed and stop.

### 4. Self-review before finishing

Re-read your diff and remove:
- Tests that only validate Pydantic shape (Pydantic already validates).
- Smoke assertions that can't tell success from regression (`assert result is not None`).
- Docstrings/comments on short tests — the test name is the spec.
- `try/except` where `pytest.raises(...)` is idiomatic.
- Fixtures created for single use.
- `@pytest.mark.skip` without an explicit reason in the marker.
- Any leaked secret in test data (real-looking `sk-ant-...` tokens — use obvious placeholders like `sk-ant-test-FAKE`).

## Output to user (≤8 lines)

- Phase(s) processed.
- # cases planned, # cases written, # pending.
- Test files created/updated.
- pytest result: PASS/FAIL + count.
- Any code ↔ notes divergence detected and how it was resolved.

## What NOT to do

- Do not edit `src/` — this skill only writes `tests/` and updates the todo's Tests checklist.
- Do not generate cases for `[ ]` items in the todo (not implemented).
- Do not duplicate coverage that already exists.
- Do not skip without an explicit reason.
- Do not `git commit` — the user decides.
- Do not run `pytest -x` or `--no-cov` to hide failures. Run the full module suite.
- Do not write tests that hit the real network (no live `gh api`, no live `api.anthropic.com`). The tests must be hermetic.
- Do not write isolated unit tests for individual heuristic regex functions — exercise them through `classify()` or the spell that calls them. CLI integration only.
