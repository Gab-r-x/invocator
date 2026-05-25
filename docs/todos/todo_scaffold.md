# Scaffold — `invocator` MVP

End-to-end goal of this todo: a user runs `pipx install invocator`, then `invocator forge key` (one-time pact), then `invocator extract wisdom --repo OleveCo/CourseGPTBackend`, and ends up with a `learnings/` folder of markdown files synthesizing the project's accumulated knowledge from PRs, issues, commits, and code reviews.

Three public spells in v1:

- `invocator forge key` — binds a pact with the Anthropic API (stores the key)
- `invocator scry cost --repo X` — gazes ahead at $/time/items before the ritual
- `invocator extract wisdom --repo X` — the full ritual (summon → transmute → inscribe internally)

Internal modules (`summon`, `transmute`, `inscribe`) are not exposed as spells in v1.

---

## Phase 1 — Skeleton & install

- [ ] `pyproject.toml` with Typer entrypoint `invocator = "invocator.cli:app"`, deps: `typer>=0.12`, `rich>=13`, `pydantic>=2`, `anthropic>=0.40`, `python-dateutil`. Dev: `pytest`, `pytest-mock`, `ruff`, `pyright`, `freezegun`.
- [ ] `src/invocator/__init__.py` exports `__version__`.
- [ ] `src/invocator/cli.py` — Typer `app` with three command groups (`forge`, `scry`, `extract`) registered as `app.add_typer(...)`. Each group has one subcommand stub (`key`, `cost`, `wisdom`) printing "not yet implemented" via Rich.
- [ ] `src/invocator/config.py` — `Settings` Pydantic model (paths, defaults). No I/O yet.
- [ ] `src/invocator/result.py` — `Result[T]` generic (mirror of STANDARDS Rule 3 shape).
- [ ] `src/invocator/models.py` — pydantic models stubbed: `PullRequest`, `Issue`, `Commit`, `ReviewComment`, `IssueComment`, `ClassifiedItem`. Only fields needed for v1.
- [ ] `LICENSE` (MIT), `.gitignore` (ignores `.cache/`, `learnings/`, `dist/`, `*.egg-info/`, `__pycache__/`), `README.md` stub.
- [ ] `pip install -e . --quiet` succeeds; `invocator --help` lists `forge`, `scry`, `extract` groups.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 2 — `forge key` (binding the pact)

- [ ] `src/invocator/commands/forge.py` — Typer sub-app with `key` subcommand.
- [ ] Interactive flow: prompt for Anthropic API key (hidden input via `typer.prompt(hide_input=True)`).
- [ ] Validate the key with a single low-cost call (e.g. `client.messages.create` with `max_tokens=1`, `model="claude-haiku-4-5-20251001"`) before saving. On invalid key, return `Result` with `error_code=INVALID_API_KEY`; print masked failure via Rich.
- [ ] Save to `~/.invocator/config.toml` with `os.chmod(path, 0o600)`. Schema: `[anthropic] api_key = "..."`.
- [ ] `forge key --show` prints masked key (`sk-ant-***...XYZ4`); never the full key.
- [ ] `forge key --unset` deletes the entry; idempotent.
- [ ] `ANTHROPIC_API_KEY` env var overrides the config file when present (logged once at info level).
- [ ] Helper `config.load_api_key() -> Result[str]` consumed by spells that need it; returns `error_code=NO_API_KEY` when absent.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 3 — `gh` client + repo binding

- [ ] `src/invocator/gh_client.py` — module-level async wrapper around `gh` subprocess.
- [ ] `check_gh_installed() -> Result[None]` — `which gh` + version check; returns `error_code=GH_NOT_INSTALLED` with install URL on failure.
- [ ] `check_auth() -> Result[None]` — `gh auth status`; returns `error_code=GH_NOT_AUTHENTICATED` on failure.
- [ ] `run_gh(args, *, paginate=False) -> bytes` — subprocess wrapper; raises on non-zero except for handled rate-limit case.
- [ ] Rate-limit handling: on 403/429 surfaced by gh, read `gh api rate_limit`, sleep until reset, retry (max 3 attempts). Logged at warning level.
- [ ] `parse_repo(value: str) -> Result[RepoRef]` — accepts `owner/name`, `https://github.com/owner/name`, with or without `.git`; returns `RepoRef(owner, name)` pydantic model.
- [ ] `get_default_branch(*, repo: RepoRef) -> Result[str]` — calls `gh api repos/{owner}/{name}` once; reads `default_branch`.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 4 — `scry cost`

- [ ] `src/invocator/commands/scry.py` — Typer sub-app with `cost` subcommand. Args: `--repo` (required), `--model` (default `claude-sonnet-4-6`), `--since` (optional), `--json` (output mode).
- [ ] Internal `probe_endpoint(*, endpoint: str) -> Result[int]` — `gh api <endpoint>?per_page=1 -i`, parses `Link: ...rel="last"` for total page count; returns estimated item count (≤ pages × 100).
- [ ] Probe all six endpoints: `pulls?state=all`, `issues?state=all`, `pulls/comments`, `issues/comments`, `commits?sha={default_branch}`. (Skip per-PR `reviews` — flagged `--deep-reviews` in future phases.)
- [ ] `estimate_cost(*, item_counts, model) -> CostEstimate` — pydantic model with `estimated_tokens`, `estimated_cost_usd_cents`, `estimated_minutes`. Heuristic: ~30% of raw items signal-bearing, ~200 tokens/classified-item, 5 categories.
- [ ] Rich table output: rows per resource (count), totals row, $/time prediction. `--json` mode prints `CostEstimate.model_dump_json()` to stdout.
- [ ] Exits 0 even on partial probes (some endpoints 404 in older repos); flags missing endpoints in output.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 5 — Cache + summon internals

- [ ] `src/invocator/cache.py` — JSONL utilities: `append_jsonl(path, items)`, `read_jsonl(path)`, `merge_by_id(*, path, items, id_field) -> int` (atomic via `.tmp` + `os.replace`), `load_watermark(repo) -> dict`, `save_watermark(repo, dict)`.
- [ ] Cache root resolution: `--cache-dir` flag > `INVOCATOR_CACHE_DIR` env > `./.cache/invocator/` default. Layout: `{cache_root}/{owner}__{name}/{resource}.jsonl` + `watermark.json`.
- [ ] `src/invocator/summon.py` — `summon_all(*, repo, settings) -> Result[SummonStats]`. Internal function (no Typer command in v1).
- [ ] Per-resource fetchers using `gh api --paginate`: PRs, issues, commits, pulls/comments, issues/comments. Each updates its own watermark on success.
- [ ] `--exclude-bots` default ON: drops authors matching `dependabot[bot]`, `renovate[bot]`, `github-actions[bot]` at the parse step; drops commits whose message starts with `Merge pull request`/`Merge branch`.
- [ ] Rich progress bar per resource (line per fetch, item count update).

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 6 — Transmute internals (classify)

- [ ] `src/invocator/classify.py` — `classify(*, cache_dir, repo) -> Result[ClassifiedStats]`. Reads cached JSONL, writes `classified/<category>.jsonl`.
- [ ] `src/invocator/rules/conventional.py` — regex on conventional commit prefixes; maps to `Category`.
- [ ] `src/invocator/rules/review_cues.py` — regex on imperative cues (`always/never/must/should/avoid/prefer`) and bug-pattern cues (`regress/race condition/deadlock/leak`); extracts one-sentence snippet window.
- [ ] `src/invocator/rules/labels.py` — default label → category map; overridable via `[tool.invocator.labels]` in `pyproject.toml` of the **invocator project itself** (the tool's own defaults), and via `--labels-config PATH` flag for end-user overrides.
- [ ] `src/invocator/rules/adr.py` — detect ADR-style PR bodies (`## Context`/`## Decision`/`## Consequences` ≥ 2 of 4) and `ADR-` title prefix.
- [ ] Glossary mining: count capitalized multi-word phrases and backticked terms across titles+labels; threshold ≥3 occurrences.
- [ ] Dedupe: SHA1 of normalized snippet → drop exact dupes per category.
- [ ] Top-K cap: sort by `weight` desc, keep top `--top-k` (default 500) per category.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 7 — Inscribe internals (LLM synthesis)

- [ ] `src/invocator/synthesize.py` — `synthesize_all(*, classified_dir, out_dir, model, dry_run) -> Result[SynthesisStats]`. Internal.
- [ ] `src/invocator/prompts.py` — five category prompts (`RULES`, `PREVENCOES`, `PATTERNS`, `DECISIONS`, `GLOSSARY`) + `INDEX` prompt. Each is a constant string template.
- [ ] One Anthropic call per category + one for `INDEX.md`. Each call uses three message blocks: system (cached `ephemeral`), corpus bundle (cached `ephemeral`), instruction (uncached).
- [ ] `count_tokens(*, system, corpus) -> int` via `client.messages.count_tokens(...)`; refuse to call if > 200k tokens unless `--force`.
- [ ] `log_usage(*, response, category)` — reads `response.usage`, computes USD cost from model pricing table, logs via Rich (`Used 78k input / 4.2k output / cache_read 2k → $0.31 for rules`).
- [ ] Synthesis cache: SHA1 of corpus bundle stored at `learnings/.cache/<category>.hash`. Hash match → skip LLM, reuse `learnings/<category>.md.cached`. Hash mismatch → call LLM, write both `.md` and `.hash`.
- [ ] `--dry-run` skips Anthropic; writes raw bullet dumps of classified snippets to `learnings/<category>.md` for inspection.
- [ ] Render `learnings/INDEX.md` with repo, run timestamp, watermark, per-file bullet count, one-line description.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 8 — `extract wisdom` (the full ritual)

- [ ] `src/invocator/commands/extract.py` — Typer sub-app with `wisdom` subcommand. Args: `--repo` (required), `--since`, `--out` (default `./learnings`), `--cache-dir`, `--model` (default `claude-sonnet-4-6`), `--top-k 500`, `--dry-run`, `--yes` (skip cost confirmation), `--force-refetch`.
- [ ] Pipeline: `forge`-check (Result error if no API key and not `--dry-run`) → `gh_client.check_installed + check_auth` → `summon_all` → `classify` → `synthesize_all`.
- [ ] Before `summon_all`: run the same probe as `scry cost`, print the table, **prompt for confirmation** unless `--yes`. On "no", exit 0 with `Aborted by user`.
- [ ] Any step returning `Result(success=False)` aborts the run with the right exit code and Rich error panel; preceding successful steps' cache is preserved (re-run is cheap).
- [ ] Final Rich summary: where the `learnings/` files were written, how many entries per file, total $ spent.
- [ ] E2E smoke target: `invocator extract wisdom --repo OleveCo/CourseGPTBackend --dry-run --top-k 50` completes without network calls beyond `gh api`, produces 5 files + INDEX in `./learnings/`.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>

---

## Phase 9 — Distribution

- [ ] `README.md` real content: install (`pipx install invocator`), prerequisites (`gh auth login`), quickstart (3 spells), troubleshooting.
- [ ] `CHANGELOG.md` — `0.1.0` entry.
- [ ] `.github/workflows/ci.yml` — runs `black --check`, `isort --check-only`, `flake8`, `pyright`, `pytest` on push/PR. Matrix: Python 3.11, 3.12.
- [ ] `.github/workflows/release.yml` — triggers on tag `v*`: `uv build` (or `python -m build`), `twine upload` to PyPI using `${{ secrets.PYPI_TOKEN }}`, attach wheel to GitHub Release.
- [ ] Pre-publish dry run: `python -m build && twine check dist/*`. Verify `gh-extractor` is not the name conflicting with `invocator` on PyPI (search PyPI before first publish).
- [ ] Tag `v0.1.0`, run release workflow, confirm `pipx install invocator` works on a clean machine.

### Implementation Notes

<filled by /todo-progress>

### Tests

<filled by /todo-tests>
