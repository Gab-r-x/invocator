# Claude Code Instructions — invocator (project-specific rules)

> **Read [docs/STANDARDS.md](docs/STANDARDS.md) before every task.** It is the single source of truth for coding patterns. These project rules override the general user-level `CLAUDE.md`.

---

## Quick Reference

```bash
# Local dev (no server — invocator is a CLI)
pip install -e .                   # editable install
invocator --help                   # entrypoint check
invocator forge key                # set/replace Anthropic API key
invocator scry cost --repo owner/name   # cost preview before a real run
invocator extract wisdom --repo owner/name --dry-run --top-k 50   # smoke

# Prerequisites the tool delegates to
gh --version                       # gh CLI required (no direct GitHub HTTP)
gh auth status                     # gh must be authenticated
```

```bash
# Tests (CLI integration only — no live network)
pytest tests/ -v

# Lint / typecheck
black --check --line-length=100 src/ tests/
isort --check-only --profile=black src/ tests/
flake8 --max-line-length=100 src/ tests/
pyright src/
```

```bash
# Anthropic API key — stored in ~/.invocator/config.toml (chmod 600)
# Override with env: ANTHROPIC_API_KEY=...
# NEVER print, log, or commit the unmasked key. Mask as sk-ant-***...XYZ4.
```

---

## Workflow (6 phases)

### 1. Understand

Before writing any code, ensure these are clear — ask one or two questions at a time until resolved:

- **Goal** — what is this task trying to achieve?
- **Definition of success** — what does "done" look like?
- **Relevant code** — which files, spells, or modules are in scope?
- **Edge cases and risks** — large repos, rate limits, missing `gh auth`, cost surprises?
- **Testing scope** — which CLI paths need integration tests? Any new fixtures needed under `tests/fixtures/gh_api/`?
- **Open questions** — anything to think through before implementation starts?

Then read:

- **Relevant source files** — understand what exists before proposing changes.
- **[docs/STANDARDS.md](docs/STANDARDS.md)** for the 16 coding rules.
- **[docs/todos/README.md](docs/todos/README.md)** for the executor → progress → tests pipeline.
- **Available skills** — check `.claude/skills/` (`todo-orchestrator`, `todo-executor`, `todo-progress`, `todo-tests`).

Never start implementation with unresolved ambiguity.

### 2. Plan

For non-trivial work (3+ files, architectural decisions, new spells):

- **Phased todo** → `docs/todos/todo_<feature>.md`. Driven by `/todo-orchestrator`. See [docs/todos/README.md](docs/todos/README.md) for structure.
- Identify all files that will change.
- Define test cases per spell path: scenario, input fixture, expected output. Concrete enough to validate before implementation.
- List documentation changes — which docs will be updated and what will change.
- Note any cache or config schema changes and the backward-compatibility approach.
- **Present the plan for user approval** before implementing.

Skip planning for trivial changes (regex tweak, single-flag addition, typo fix).

### 3. Implement

- **Branch from `origin/main`**: `git checkout -b <type>/<short-description> origin/main`.
- **Create a draft PR immediately** after the first commit — gives visibility into progress.
- **Commit frequently** — one logical concern per commit. Use `<type>: <description>` format.
- **Use subagents to parallelise independent work** — e.g. an unrelated heuristic rule module while another agent writes a Typer command.
- Follow the 16 rules in [STANDARDS.md](docs/STANDARDS.md) — no exceptions.
- **Review for bloat** before each commit: remove any code, comments, or abstractions that weren't asked for.
- `Result[T]` for expected errors; let bugs bubble; map `error_code` → CLI exit code at the top-level handler in `cli.py`.
- Tests mirror the source structure: `src/invocator/commands/scry.py` → `tests/commands/test_scry.py`.

### 4. Verify

- **Integration tests**: `pytest tests/ -v` — both existing and new must pass. Present a pass/fail summary in chat.
- **Lint/typecheck**: `black --check src/ tests/ && isort --check-only src/ tests/ && flake8 src/ tests/ && pyright src/`.
- **Runtime smoke** (when a spell changed): `pip install -e . --quiet && invocator --help && invocator <spell> --help`. If the spell has a no-network path, exercise it (`--dry-run`).
- **Hermetic only.** Never hit live `api.github.com` or `api.anthropic.com` from tests. Patch `invocator.gh_client.run_gh` and the Anthropic client factory with fixtures.
- If anything fails, fix before proceeding. Never push broken tests.

### 5. Document

Apply the documentation changes identified in the plan — only once implementation is verified and stable:

- Update [docs/STANDARDS.md](docs/STANDARDS.md) only if a rule itself changed (rare).
- Update the relevant `### Implementation Notes` block in the todo file via `/todo-progress`.
- Update `README.md` if user-facing CLI surface changed.

### 6. Complete

- After the last phase of a todo: archive it via `mkdir -p docs/past/$(date +%Y-%m) && mv docs/todos/todo_<feature>.md docs/past/$(date +%Y-%m)/`.
- **Mark the PR as ready** (remove draft status).
- Use `/commit` for structured commits.
- Use `/pr` for pull requests.

---

## Git Conventions

- **Branch naming**: `<type>/<short-description>` (e.g. `feat/forge-key`, `fix/scry-link-header-parsing`).
- **Commit format**: `<type>: <description>` (e.g. `feat: forge key spell with API validation`).
- **Types**: feat, fix, refactor, test, docs, chore.
- **Keep commits logical** — one concern per commit.

**Never on this repo:**
- **NEVER add `Co-Authored-By:` lines to any commit, PR, or message.** No Claude attribution, no agent attribution, no "Generated with" footer. This is non-negotiable.
- Force push to any branch.
- Amend published commits.
- Skip hooks (`--no-verify`).
- Commit secrets or credentials (Anthropic keys, GitHub tokens, anything in `~/.invocator/config.toml`).
- Commit caches (`.cache/`, `learnings/.cache/`) or generated `learnings/` from real runs against external repos.

---

## Key Rules (from [STANDARDS.md](docs/STANDARDS.md))

1. Pydantic at I/O boundaries (gh JSON, Anthropic, config files). No raw dicts in structured returns.
2. Keyword-only arguments (`*`) on internal functions. Typer commands exempt.
3. `Result[T]` for expected errors. Exceptions for bugs. CLI top-level maps error codes → exit codes.
4. Units in field names: `_utc`, `_seconds`, `_bytes`, `_usd_cents`, `_tokens`.
5. Enums for status / category fields. Never raw strings.
6. No dynamic attribute access (no `getattr`/`setattr`/`hasattr`) on owned objects.
7. No bare `print()` for user output — always `rich.console.Console`. Exception: `--json` mode prints raw JSON to stdout.
8. Every Anthropic call uses explicit `cache_control={"type": "ephemeral"}` on stable blocks and logs `response.usage` + USD cost.
9. No direct `api.github.com` HTTP. All GitHub access goes through `gh api` subprocess via `src/invocator/gh_client.py`.
10. JSONL cache is append-only; merges are atomic via `.tmp` + `os.replace`. Watermark updated per resource only on successful fetch.
11. Imports at top of file. No inline imports.
12. No over-engineering. Don't add what wasn't asked for.

---

## Testing

- **CLI integration only.** Exercise spells through `typer.testing.CliRunner` against the in-process Typer app.
- Tests live in `tests/` and mirror `src/invocator/`. Convention: `src/invocator/commands/scry.py` → `tests/commands/test_scry.py`.
- **Hermetic.** No live `gh api` calls, no live Anthropic calls. Patch `invocator.gh_client.run_gh` to return fixture bytes from `tests/fixtures/gh_api/`. Patch the Anthropic client factory to return canned `Message` objects.
- **Filesystem.** Use `tmp_path` for any cache or config writes. Never touch the real `~/.invocator/`.
- Models, heuristic rules, and synthesis are exercised through spell-level tests, not in isolation.
- Secrets in test data must be obvious fakes (`sk-ant-test-FAKE`), never anything that looks real.

---

## Cache & Config Schema Changes

When changing the layout of `~/.invocator/config.toml` or `.cache/invocator/`:

- **Pre-1.0 (current):** schema changes are free. Bump a `schema_version` field at the top of the file; the loader can refuse to read unknown versions with a clear error.
- **Post-1.0:** add a migration step in `src/invocator/config.py` (for config) or `src/invocator/cache.py` (for cache layout). Migrations must be idempotent and run on first read of the old version.

Never silently overwrite a user's config. If a migration is destructive (renaming a key), prompt before applying.

---

## Blockers

If you hit a blocker (missing `gh` auth, unexpected GitHub API shape, Anthropic rate limit, unclear requirement), stop immediately and use this format:

> **Blocker:** [what is blocking you]
> **Tried:** [what you've already attempted]
> **Options:**
> 1. [Option A]
> 2. [Option B]
> **What should I do?**

Never guess, assume, or work around silently.
