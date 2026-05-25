# Scaffold — `invocator` MVP

End-to-end goal of this todo: a user runs `pipx install invocator`, then `invocator forge key` (one-time pact), then `invocator extract wisdom --repo OleveCo/CourseGPTBackend`, and ends up with a `learnings/` folder of markdown files synthesizing the project's accumulated knowledge from PRs, issues, commits, and code reviews.

Three public spells in v1:

- `invocator forge key` — binds a pact with the Anthropic API (stores the key)
- `invocator scry cost --repo X` — gazes ahead at $/time/items before the ritual
- `invocator extract wisdom --repo X` — the full ritual (summon → transmute → inscribe internally)

Internal modules (`summon`, `transmute`, `inscribe`) are not exposed as spells in v1.

---

## Phase 1 — Skeleton & install [x]

- [x] `pyproject.toml` with Typer entrypoint `invocator = "invocator.cli:app"`, deps: `typer>=0.12`, `rich>=13`, `pydantic>=2`, `anthropic>=0.40`, `python-dateutil`. Dev: `pytest`, `pytest-mock`, `ruff`, `pyright`, `freezegun`.
- [x] `src/invocator/__init__.py` exports `__version__`.
- [x] `src/invocator/cli.py` — Typer `app` with three command groups (`forge`, `scry`, `extract`) registered as `app.add_typer(...)`. Each group has one subcommand stub (`key`, `cost`, `wisdom`) printing "not yet implemented" via Rich.
- [x] `src/invocator/config.py` — `Settings` Pydantic model (paths, defaults). No I/O yet.
- [x] `src/invocator/result.py` — `Result[T]` generic (mirror of STANDARDS Rule 3 shape).
- [x] `src/invocator/models.py` — pydantic models stubbed: `PullRequest`, `Issue`, `Commit`, `ReviewComment`, `IssueComment`, `ClassifiedItem`. Only fields needed for v1.
- [x] `LICENSE` (MIT), `.gitignore` (ignores `.cache/`, `learnings/`, `dist/`, `*.egg-info/`, `__pycache__/`), `README.md` stub.
- [x] `pip install -e . --quiet` succeeds; `invocator --help` lists `forge`, `scry`, `extract` groups.

### Implementation Notes

- **Files:** `pyproject.toml`, `src/invocator/__init__.py`, `src/invocator/cli.py`, `src/invocator/config.py`, `src/invocator/result.py:8`, `src/invocator/models.py`, `LICENSE`, `.gitignore`, `README.md`
- **Public entry points:** `invocator forge key`, `invocator scry cost`, `invocator extract wisdom` (all stubs that print "not yet implemented" via Rich). Console script wired via `[project.scripts] invocator = "invocator.cli:app"`.
- **Key behaviors / invariants:**
  - All three sub-apps (`forge_app`, `scry_app`, `extract_app`) registered on root `app` via `app.add_typer(..., name=...)`.
  - Each stub command returns `None` cleanly and writes a yellow Rich tag (`[yellow]<cmd>:[/yellow] not yet implemented`) to the module-level `console`.
  - `Result[T]` is `BaseModel, Generic[T]` with fields `success`, `data`, `error_message`, `error_context`, `error_code`, `error_grouping_prefix`; helper methods `add_context(*, key, value)` (mutates + returns self) and `get_error_message()` (composes `[CODE] message (k=v, ...)`).
  - `Settings` is pure config (no I/O): `cache_dir`, `out_dir`, `model="claude-sonnet-4-6"`, `top_k_per_category=500`, `exclude_bots=True`, with `Path` defaults via `Field(default_factory=...)`.
  - `models.Category` is a `str, Enum` with the five v1 categories (`rules`, `prevencoes`, `patterns`, `decisions`, `glossary`).
  - `RepoRef(owner, name)` is defined in `models.py` (Phase 3 will import from here; not from `gh_client`).
- **Edge cases observed in code:**
  - `cli.py` registers sub-apps and the lone subcommand stubs in a single module — no `src/invocator/commands/` package yet (Phase 2 will create it; current stubs live inline in `cli.py` and will need to move).
  - `pyproject.toml` triggers a pyright "could not be parsed" warning but it does not block typecheck (0 errors / 0 warnings on `src/`). Hatchling build still works.
  - `.gitignore` ignores `.invocator/` and `config.toml` at repo root, important for Phase 2's `~/.invocator/config.toml` flow not leaking via accidental copy.
- **Result[T] usage:**
  - No call sites yet — this phase only defines the shape. Future phases should return `Result[T]` rather than raise for expected failures; populate `error_code` with stable identifiers (`NO_API_KEY`, `GH_NOT_INSTALLED`, etc.) and use `add_context(key=..., value=...)` for diagnostic data.
- **Not yet implemented (referenced by todo):**
  - Nothing in scope for Phase 1 is missing. The `src/invocator/commands/` package referenced by Phases 2/4/8 will be created later; today the stubs live in `cli.py`.
- **Test hooks / seams:**
  - `from invocator.cli import app` is importable; use `typer.testing.CliRunner().invoke(app, [...])` against it.
  - `console` is module-level in `cli.py` — patch via `monkeypatch.setattr("invocator.cli.console", fake_console)` if a test needs to capture Rich output deterministically.
  - `Settings()` can be instantiated with no args (all defaults); override fields per test via kwargs.
  - `Result[int](success=True, data=5)` parametrization works at runtime (pydantic + Generic), so tests can assert on concrete generics.

### Tests

**Target file(s):** `tests/test_cli_smoke.py`, `tests/test_result.py`, `tests/test_config.py`, `tests/test_models.py`

**Cases to cover:**
- [x] happy: `invocator --help` exit 0, output lists `forge`, `scry`, `extract` groups
- [x] happy: `invocator forge key` exits 0 and prints "not yet implemented"
- [x] happy: `invocator scry cost` exits 0 and prints "not yet implemented"
- [x] happy: `invocator extract wisdom` exits 0 and prints "not yet implemented"
- [x] happy: `Result[int](success=True, data=5).data == 5`
- [x] happy: `Result(success=False, error_message="boom", error_code="X").get_error_message()` contains "boom" and "[X]"
- [x] edge: `add_context(key=k, value=v)` returns self and stores the value in `error_context`
- [x] edge: `get_error_message()` on a success Result returns empty string
- [x] happy: `Settings()` instantiates with documented defaults (model, top_k_per_category, exclude_bots)
- [x] happy: `Settings(model="claude-opus-4-7")` overrides model field
- [x] happy: `Category` enum has the 5 documented values with lowercase string values
- [x] happy: `RepoRef(owner="x", name="y")` round-trips through `model_dump`
- [x] happy: `ClassifiedItem(...)` defaults `signals` to `[]`

---

## Phase 2 — `forge key` (binding the pact) [x]

- [x] `src/invocator/commands/forge.py` — Typer sub-app with `key` subcommand.
- [x] Interactive flow: prompt for Anthropic API key (hidden input via `typer.prompt(hide_input=True)`).
- [x] Validate the key with a single low-cost call (e.g. `client.messages.create` with `max_tokens=1`, `model="claude-haiku-4-5-20251001"`) before saving. On invalid key, return `Result` with `error_code=INVALID_API_KEY`; print masked failure via Rich.
- [x] Save to `~/.invocator/config.toml` with `os.chmod(path, 0o600)`. Schema: `[anthropic] api_key = "..."`.
- [x] `forge key --show` prints masked key (`sk-ant-***...XYZ4`); never the full key.
- [x] `forge key --unset` deletes the entry; idempotent.
- [x] `ANTHROPIC_API_KEY` env var overrides the config file when present (logged once at info level).
- [x] Helper `config.load_api_key() -> Result[str]` consumed by spells that need it; returns `error_code=NO_API_KEY` when absent.

### Implementation Notes

- **Files:** `src/invocator/commands/__init__.py`, `src/invocator/commands/forge.py`, `src/invocator/config.py:10-12`, `src/invocator/config.py:27-75`, `src/invocator/cli.py:4`, `src/invocator/cli.py:12`, `pyproject.toml:21`
- **Public entry points:** `invocator forge key`, `invocator forge key --show`, `invocator forge key --unset`, `config.load_api_key() -> Result[str]`
- **Key behaviors / invariants:**
  - Validation uses a single `anthropic.Anthropic(api_key=...).messages.create(model="claude-haiku-4-5-20251001", max_tokens=1, messages=[{"role":"user","content":"ping"}])` ping; on success the response is discarded.
  - Mask format on `--show` and on validation-failure error line: `sk-ant-***...XYZ4` (first 7 chars + `***...` + last 4); short keys (≤11 chars) mask to `***`.
  - Config is written atomically via a `.tmp` sibling + `os.replace`, then `os.chmod(path, 0o600)` is applied on every write (set/unset path).
  - `CONFIG_DIR` (`~/.invocator`) is created with `mkdir(parents=True, exist_ok=True)` before write (both inside `_write_config` and again at command level).
  - `ANTHROPIC_API_KEY` env var, when present and truthy, overrides the config file in `load_api_key()`. The override is logged exactly once per process at `INFO` via the module-level `logger` (guarded by `_env_logged` flag in `invocator.config`).
  - `forge key --unset` is idempotent: returns exit 0 with a yellow "nothing to unset" message when no config file exists or when no `api_key` is stored.
  - `--show` and `--unset` are mutually exclusive (exit code 2 if both passed).
- **Edge cases observed in code:**
  - `--show` with no config file (or no `[anthropic].api_key`): prints `"No Anthropic API key configured."` and exits 0 (not an error).
  - `--unset` with no config file at all: prints `"No config file present; nothing to unset."` exit 0. `--unset` with file but no `api_key`: prints `"No API key stored; nothing to unset."` exit 0.
  - When unsetting, if the `[anthropic]` section becomes empty after deletion, the section itself is removed (`data.pop("anthropic", None)`) so the file doesn't carry an empty table.
  - Empty/whitespace-only prompted key (after `.strip()`) exits 1 with `"Empty API key provided."`.
  - Exceptions caught around `Anthropic.messages.create()`: `anthropic.AuthenticationError` → `error_code=INVALID_API_KEY`; `anthropic.APIStatusError` → `error_code=API_STATUS_ERROR`. Other exceptions propagate.
  - `config._read_config_file` catches `OSError` (`CONFIG_READ_FAILED`) and `tomllib.TOMLDecodeError` (`CONFIG_PARSE_FAILED`), each with `path` context.
- **Result[T] usage:**
  - `load_api_key() -> Result[str]`: success carries the key string; failures use `error_code` in {`NO_API_KEY`, `CONFIG_READ_FAILED`, `CONFIG_PARSE_FAILED`}.
  - `_validate_api_key(*, api_key) -> Result[None]`: success on validated key; failures use `INVALID_API_KEY` or `API_STATUS_ERROR`.
  - `_read_config_file(*, path) -> Result[dict]`: returns `data={}` on missing file (success), wraps read/parse errors.
- **Test hooks / seams:**
  - `invocator.config.CONFIG_FILE` and `invocator.config.CONFIG_DIR` are module-level `Path` constants — patch via `monkeypatch.setattr("invocator.config.CONFIG_FILE", tmp_path / "config.toml")` (and the matching `CONFIG_DIR`). The forge module imports them by name (`from invocator.config import CONFIG_DIR, CONFIG_FILE`), so patching needs to target `invocator.commands.forge.CONFIG_FILE` / `CONFIG_DIR` to affect the `forge key` command path.
  - `invocator.commands.forge.anthropic` is the imported `anthropic` module — patch `invocator.commands.forge.anthropic.Anthropic` (or `monkeypatch.setattr("invocator.commands.forge.anthropic", fake_module)`) to inject a fake client. Tests can assert the validation call shape (`model=VALIDATION_MODEL`, `max_tokens=1`, single user "ping" message).
  - `VALIDATION_MODEL` is exposed as a module-level constant in `invocator.commands.forge`.
  - Env override: `monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE")`; reset the once-logged flag via `monkeypatch.setattr("invocator.config._env_logged", False)` between tests.
  - `typer.prompt` is used for hidden-input capture — `CliRunner().invoke(app, ["forge","key"], input="sk-ant-...\n")` works.
- **Not yet implemented (referenced by todo):**
  - None — every Phase 2 sub-item is implemented.

### Tests

**Target file(s):** `tests/commands/test_forge.py` (mirror `src/invocator/commands/forge.py`), `tests/test_config.py` (extend existing)

**Cases to cover:**

For `tests/commands/test_forge.py`:
- [x] happy: `invocator forge key` interactive with valid key — validation passes, writes `[anthropic] api_key` to patched config, exit 0
- [x] happy: `forge key --show` with stored key prints masked form `sk-ant-***...XYZ4`, raw key absent from stdout
- [x] happy: `forge key --show` with no config file prints "No Anthropic API key configured" and exits 0
- [x] happy: `forge key --unset` with stored key removes entry, exit 0; subsequent `--show` reports no key
- [x] happy: `forge key --unset` with no config file is idempotent (exit 0, "nothing to unset")
- [x] error: `forge key` with invalid key — fake `AuthenticationError` → exit non-zero, no config file written, stderr does NOT contain raw key
- [x] error: `forge key --show --unset` (mutually exclusive) → exit code 2
- [x] error: `forge key` with empty/whitespace input → exit 1 "Empty API key provided"
- [x] edge: after successful write, `os.stat(CONFIG_FILE).st_mode & 0o777 == 0o600`

For `tests/test_config.py`:
- [x] happy: `load_api_key()` returns env var when `ANTHROPIC_API_KEY` set
- [x] happy: `load_api_key()` returns file value when env var unset
- [x] error: `load_api_key()` with neither set returns `Result(success=False, error_code="NO_API_KEY")`
- [x] edge: env var takes precedence over file when both set
- [x] edge: env override INFO log fires only once per process (call count == 1 across two calls)

---

## Phase 3 — `gh` client + repo binding [x]

- [x] `src/invocator/gh_client.py` — module-level async wrapper around `gh` subprocess.
- [x] `check_gh_installed() -> Result[None]` — `which gh` + version check; returns `error_code=GH_NOT_INSTALLED` with install URL on failure.
- [x] `check_auth() -> Result[None]` — `gh auth status`; returns `error_code=GH_NOT_AUTHENTICATED` on failure.
- [x] `run_gh(args, *, paginate=False) -> bytes` — subprocess wrapper; raises on non-zero except for handled rate-limit case.
- [x] Rate-limit handling: on 403/429 surfaced by gh, read `gh api rate_limit`, sleep until reset, retry (max 3 attempts). Logged at warning level.
- [x] `parse_repo(value: str) -> Result[RepoRef]` — accepts `owner/name`, `https://github.com/owner/name`, with or without `.git`; returns `RepoRef(owner, name)` pydantic model.
- [x] `get_default_branch(*, repo: RepoRef) -> Result[str]` — calls `gh api repos/{owner}/{name}` once; reads `default_branch`.

### Implementation Notes

- **Files:** `src/invocator/gh_client.py`
- **Public entry points:** `check_gh_installed()`, `check_auth()`, `run_gh(args, *, paginate=False) -> bytes`, `parse_repo(value) -> Result[RepoRef]`, `get_default_branch(*, repo) -> Result[str]`, exception `GhSubprocessError`
- **Key behaviors / invariants:**
  - All GitHub access flows through the `gh` subprocess (`subprocess.run` with `capture_output=True`); no `httpx`/`requests` usage anywhere in the module.
  - `run_gh(["api", ...], paginate=True)` prepends `--paginate` so the final invocation is `["gh", "--paginate", "api", ...]`.
  - Rate-limit retry loop: a non-zero `gh` call is treated as rate-limited if `returncode == 4` OR if stderr (lowercased) contains `"rate limit"` / `"api rate limit exceeded"`. The module then calls `gh api rate_limit`, sleeps `max(0, reset - now) + 1` seconds (capped at 600), logs a warning, and retries. Max 3 retries; on the 4th rate-limited response it raises `GhSubprocessError`.
  - Despite the todo's "async" wording, the implementation is synchronous (blocking `subprocess.run` + `time.sleep`). Treated as a wording carryover, not a divergence to act on.
- **Edge cases observed in code:**
  - `parse_repo` strips whitespace, then strips `https://github.com/`, `http://github.com/`, or `git@github.com:` prefixes, trims trailing `/`, strips a trailing `.git`, then splits on `/`. Owner and name must each match `re.compile(r"^[A-Za-z0-9._-]+$")` — anything else (including spaces) returns `error_code=INVALID_REPO`.
  - `get_default_branch` distinguishes "repo not found" (returncode in `{1, 4}` AND stderr contains `"Not Found"`) → `error_code=REPO_NOT_FOUND`. Any other `GhSubprocessError` is re-raised.
  - `GhSubprocessError.args` shadows `BaseException.args`; the file marks the assignment `# type: ignore[assignment]` to silence pyright while preserving the gh invocation tuple on the exception.
  - Sleep-cap exceeded (reset > 600s away) raises `GhSubprocessError` instead of waiting.
- **Result[T] usage:**
  - Error codes emitted: `GH_NOT_INSTALLED` (FileNotFoundError OR non-zero `gh --version`), `GH_NOT_AUTHENTICATED` (non-zero `gh auth status`), `INVALID_REPO` (parse failure), `REPO_NOT_FOUND` (gh "Not Found" on repos endpoint).
  - `run_gh` raises `GhSubprocessError` for non-rate-limit failures rather than returning a Result — its contract is bytes-on-success.
- **Test hooks / seams:**
  - Patch `invocator.gh_client.subprocess.run` via `monkeypatch.setattr` to inject fake `subprocess.CompletedProcess` (or raise `FileNotFoundError`) without spawning real `gh`.
  - Patch `invocator.gh_client.time.sleep` to a no-op so rate-limit tests run instantly.
  - `GhSubprocessError` is importable from `invocator.gh_client` for `pytest.raises` assertions.
  - `RepoRef` is imported from `invocator.models`; tests can construct `RepoRef(owner="x", name="y")` directly to drive `get_default_branch`.
- **Not yet implemented (referenced by todo):**
  - None — every Phase 3 sub-item is implemented.

### Tests

**Target file(s):** `tests/test_gh_client.py` (mirror `src/invocator/gh_client.py`)

**Cases to cover:**
- [x] happy: `parse_repo("owner/name")` returns `Result(success=True, data=RepoRef(owner="owner", name="name"))`
- [x] happy: `parse_repo("https://github.com/owner/name")` parses correctly
- [x] happy: `parse_repo("https://github.com/owner/name.git")` strips `.git`
- [x] happy: `parse_repo("git@github.com:owner/name.git")` parses SSH form
- [x] error: `parse_repo("garbage")` → `error_code=INVALID_REPO`
- [x] error: `parse_repo("owner/name with space")` → `error_code=INVALID_REPO`
- [x] happy: `check_gh_installed()` with successful fake subprocess returns `success=True`
- [x] error: `check_gh_installed()` with `FileNotFoundError` → `error_code=GH_NOT_INSTALLED`
- [x] error: `check_gh_installed()` with non-zero exit → `error_code=GH_NOT_INSTALLED`
- [x] happy: `check_auth()` with successful fake subprocess returns `success=True`
- [x] error: `check_auth()` with non-zero exit → `error_code=GH_NOT_AUTHENTICATED`
- [x] happy: `run_gh(["api", "..."])` returns stdout bytes when subprocess succeeds
- [x] happy: `run_gh(["api", "..."], paginate=True)` prepends `--paginate` (asserted via captured call args)
- [x] error: `run_gh(...)` with non-zero subprocess raises `GhSubprocessError` carrying `returncode` and `stderr`
- [x] edge: rate-limit retry — first call returns `rc=4` + "API rate limit exceeded" stderr; `gh api rate_limit` returns near-future reset; second call succeeds → final bytes returned and `time.sleep` was called
- [x] edge: rate-limit exhaustion — 3 consecutive rate-limited responses → raises `GhSubprocessError`
- [x] happy: `get_default_branch(repo=RepoRef("a","b"))` parses `{"default_branch": "main"}` from fake gh JSON
- [x] error: `get_default_branch(...)` with `GhSubprocessError` (rc=1, stderr "Not Found") → `error_code=REPO_NOT_FOUND`

---

## Phase 4 — `scry cost` [x]

- [x] `src/invocator/commands/scry.py` — Typer sub-app with `cost` subcommand. Args: `--repo` (required), `--model` (default `claude-sonnet-4-6`), `--since` (optional), `--json` (output mode).
- [x] Internal `probe_endpoint(*, endpoint: str) -> Result[int]` — `gh api <endpoint>?per_page=1 -i`, parses `Link: ...rel="last"` for total page count; returns estimated item count (≤ pages × 100).
- [x] Probe all six endpoints: `pulls?state=all`, `issues?state=all`, `pulls/comments`, `issues/comments`, `commits?sha={default_branch}`. (Skip per-PR `reviews` — flagged `--deep-reviews` in future phases.)
- [x] `estimate_cost(*, item_counts, model) -> CostEstimate` — pydantic model with `estimated_tokens`, `estimated_cost_usd_cents`, `estimated_minutes`. Heuristic: ~30% of raw items signal-bearing, ~200 tokens/classified-item, 5 categories.
- [x] Rich table output: rows per resource (count), totals row, $/time prediction. `--json` mode prints `CostEstimate.model_dump_json()` to stdout.
- [x] Exits 0 even on partial probes (some endpoints 404 in older repos); flags missing endpoints in output.

### Implementation Notes

- **Files:** `src/invocator/commands/scry.py`, `src/invocator/cli.py:5`, `src/invocator/cli.py:13`, `src/invocator/models.py:74-86`
- **Public entry points:** `invocator scry cost`, `scry.probe_endpoint(*, endpoint)`, `scry.estimate_cost(*, item_counts, model)`, pydantic model `CostEstimate` (`estimated_tokens`, `estimated_cost_usd_cents`, `estimated_minutes`, `per_resource`)
- **Key behaviors / invariants:**
  - Pre-checks run in order and exit 2 with a Rich `[red]✗[/red]` line on failure: `check_gh_installed`, `check_auth`, `parse_repo(value=repo)`, `get_default_branch(repo=...)`.
  - Probes 5 endpoints sequentially (the todo says "six" but only five are implemented; per-PR `reviews` is deliberately out of scope): `repos/{o}/{n}/pulls?state=all`, `.../issues?state=all`, `.../pulls/comments`, `.../issues/comments`, `.../commits?sha={default_branch}`. Resource keys: `pulls`, `issues`, `pulls_comments`, `issues_comments`, `commits`.
  - `probe_endpoint` invokes `run_gh(["api", "-i", "{endpoint}{?|&}per_page=1"])`. It splits the response on `\n\n` (falls back to `\r\n\r\n`) into header block + body. Header lookup is case-insensitive (`line.lower().startswith("link:")`).
  - Link parsing regex: `<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"` → returns `last_page * 100`.
  - Link header absent → JSON-decode the body; `list` → `len(payload)`; non-list / blank / `JSONDecodeError` → `0`.
  - 404 errors (stderr contains "Not Found") set `error_context["reason"] = "not_found"`; the caller maps that to count = 0. Any other `GhSubprocessError` becomes a `PROBE_FAILED` Result that surfaces in `failed_resources` (rendered as "—" in the table; absent from `item_counts` and `total_items`).
  - Pricing table (`MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION` in `models.py`): sonnet `claude-sonnet-4-6` → 300, opus `claude-opus-4-7` → 1500, haiku `claude-haiku-4-5` → 100. Default fallback for unknown models → 300 (`_DEFAULT_PRICING_CENTS_PER_MILLION`).
  - Heuristic constants in `scry.py`: `_SIGNAL_RATIO = 0.30`, `_TOKENS_PER_ITEM = 200`, `_NUM_CATEGORIES = 5` (constant defined but corpus tokens are not multiplied by category count — caching makes per-category overhead negligible).
  - `estimated_minutes = max(1, round(total_tokens / 1_000_000 * 2))`.
  - `--json` mode (Typer option `json_output`) bypasses the Rich table and emits the JSON via `console.print_json(json.dumps(estimate.model_dump()))` (STANDARDS Rule 13 exception documented in the source); then returns early.
  - Rich table title is `Scry cost — {owner}/{name} (model={model})`; columns `Resource` and `Estimated items`; bottom row labelled `[bold]total[/bold]`. After the table, a single line prints `Estimated tokens`, `Cost` (dollars with 2 decimals), `Wall time` (in minutes).
- **Edge cases:**
  - `--since` is currently informational only — the option is accepted, printed as a `[dim]` line in table mode, and not propagated to probes (deviation recorded; Phase 5+ concern).
  - Typer option `json_output` uses `--json` as the CLI flag to avoid shadowing the `json` stdlib module imported at module top.
  - When `Link: ...rel="last"` is absent, falls back to JSON-array length from the response body (single-page repos).
  - Empty body / non-list JSON / decode failure all collapse to count = 0 (safe degrade).
- **Result[T] usage:** `probe_endpoint` returns `Result[int]`; on subprocess failure error_code = `PROBE_FAILED` with `error_context["endpoint"]`, `error_context["returncode"]`, and `error_context["reason"]="not_found"` when applicable. Pre-checks reuse codes from `gh_client.py`: `GH_NOT_INSTALLED`, `GH_NOT_AUTHENTICATED`, `INVALID_REPO`, `REPO_NOT_FOUND`.
- **Test hooks / seams:**
  - `invocator.commands.scry.run_gh`, `invocator.commands.scry.parse_repo`, `invocator.commands.scry.get_default_branch`, `invocator.commands.scry.check_gh_installed`, `invocator.commands.scry.check_auth` are all module-level names (re-imported into `scry`) — patch with `monkeypatch.setattr("invocator.commands.scry.<name>", fake)`.
  - `GhSubprocessError` is imported from `invocator.gh_client`; build instances with `GhSubprocessError(returncode=..., stderr=b"...", args=[...])` to drive the 404 / generic-error branches via a patched `run_gh` that raises.
  - `invocator.commands.scry.console` (stdout) and `invocator.commands.scry.err_console` (stderr) are module-level Rich consoles — `CliRunner` captures their output via stdout/stderr already.
- **Not yet implemented (referenced by todo):**
  - `--since` date filtering on probes (accepted as CLI flag but unused; deferred to Phase 5+).
  - Per-PR `reviews` endpoint probe (todo mentions skipping it behind `--deep-reviews`; not present yet).

### Tests

**Target file(s):** `tests/commands/test_scry.py` (mirror `src/invocator/commands/scry.py`), `tests/test_cli_smoke.py` (existing smoke updated to match new contract)

**Cases to cover:**
- [x] happy: `scry cost --repo owner/name --json` with all probes succeeding → exit 0, JSON has `estimated_tokens`, `estimated_cost_usd_cents`, `per_resource` with the 5 resource keys
- [x] happy: Rich table mode (no `--json`) prints table with `pulls`, `issues`, `Estimated tokens`, `Cost`
- [x] happy: `--model claude-opus-4-7` produces exactly 5x the cost of `claude-sonnet-4-6` for the same item counts (via `estimate_cost`)
- [x] edge: one endpoint returns `GhSubprocessError` with stderr "Not Found" → count for that resource = 0, total still computed, exit 0
- [x] edge: one endpoint raises a generic `GhSubprocessError` → resource rendered as `—` in the table, exit 0
- [x] edge: Link header with `rel="last"` page=7 → `probe_endpoint` returns 700
- [x] edge: no Link header → `probe_endpoint` falls back to JSON-array length of body
- [x] error: `check_gh_installed` fails → exit 2, clean stderr message, no traceback
- [x] error: `check_auth` fails → exit 2
- [x] error: `parse_repo("garbage")` fails → exit 2
- [x] error: `get_default_branch` returns `REPO_NOT_FOUND` → exit 2
- [x] happy: `estimate_cost(item_counts={...}, model="claude-sonnet-4-6")` returns `CostEstimate` with `estimated_tokens > 0`, `estimated_cost_usd_cents >= 0`, `estimated_minutes >= 1`, `per_resource` preserved
- [x] update: `tests/test_cli_smoke.py::test_scry_cost_stub` rewritten — invoking `scry cost` with no `--repo` now exits 2 (Typer missing-required-arg)

---

## Phase 5 — Cache + summon internals [~]

- [x] `src/invocator/cache.py` — JSONL utilities: `append_jsonl(path, items)`, `read_jsonl(path)`, `merge_by_id(*, path, items, id_field) -> int` (atomic via `.tmp` + `os.replace`), `load_watermark(repo) -> dict`, `save_watermark(repo, dict)`.
- [~] Cache root resolution: `--cache-dir` flag > `INVOCATOR_CACHE_DIR` env > `./.cache/invocator/` default. Layout: `{cache_root}/{owner}__{name}/{resource}.jsonl` + `watermark.json`.
- [x] `src/invocator/summon.py` — `summon_all(*, repo, settings) -> Result[SummonStats]`. Internal function (no Typer command in v1).
- [x] Per-resource fetchers using `gh api --paginate`: PRs, issues, commits, pulls/comments, issues/comments. Each updates its own watermark on success.
- [x] `--exclude-bots` default ON: drops authors matching `dependabot[bot]`, `renovate[bot]`, `github-actions[bot]` at the parse step; drops commits whose message starts with `Merge pull request`/`Merge branch`.
- [~] Rich progress bar per resource (line per fetch, item count update).

### Implementation Notes

- **Files:** `src/invocator/cache.py`, `src/invocator/summon.py`, `src/invocator/models.py:20-43`, `src/invocator/models.py:91-99`, `src/invocator/config.py:13`, `src/invocator/config.py:79-83`
- **Public entry points:** `cache.cache_root(*, settings)`, `cache.repo_cache_dir(*, settings, repo)`, `cache.read_jsonl(path)`, `cache.append_jsonl(*, path, items)`, `cache.merge_by_id(*, path, items, id_field)`, `cache.load_watermark(*, settings, repo)`, `cache.save_watermark(*, settings, repo, watermark)`, `cache.update_resource_watermark(*, settings, repo, resource, timestamp_utc)`, exception `cache.CacheCorruptError(path, line_number, original_error)`; `summon.summon_all(*, settings, repo, since=None) -> Result[SummonStats]`; pydantic `models.SummonStats`; `config.resolve_cache_dir(*, settings) -> Path`; env constant `config.ENV_CACHE_DIR = "INVOCATOR_CACHE_DIR"`.
- **Key behaviors / invariants:**
  - Cache layout: `{settings.cache_dir}/{owner}__{name}/{resource}.jsonl` + `watermark.json`. `repo_cache_dir` creates the dir with `mkdir(parents=True, exist_ok=True)`.
  - Resource keys: `pulls`, `issues`, `commits`, `pr_review_comments`, `issue_comments`.
  - `merge_by_id` is atomic via `.tmp` sibling + `os.replace(tmp_path, path)`; preserves insertion order from `existing` then new keys in arrival order; returns `(added, updated)` tuple.
  - `append_jsonl` short-circuits on empty `items` (returns 0, does NOT touch the file).
  - `read_jsonl(missing_path)` returns `[]`; corrupt line raises `CacheCorruptError(path, line_number, json.JSONDecodeError)`. Skips blank lines.
  - `save_watermark` writes JSON indented; atomic via `.tmp` + `os.replace`.
  - `update_resource_watermark` writes `watermark["per_resource"][resource]` (ISO8601 with `Z` suffix), and ALSO refreshes `watermark["last_run_utc"]` (also `Z`-suffixed via `_utc_now_iso`). All other per-resource entries are preserved.
  - Watermarks are updated only on successful fetch of THAT resource — failures abort `summon_all` mid-loop without touching later resources' watermarks.
  - ISO8601 timestamps everywhere use `Z` suffix (not `+00:00`); produced by `_to_iso_z` / `_utc_now_iso` in both `cache.py` and `summon.py`.
  - `--paginate` + `--jq '.[]'` → newline-delimited JSON; `_paginate_jsonl` decodes utf-8 and json-loads each non-blank line.
  - `pulls` endpoint URL: `repos/{o}/{n}/pulls?state=all&sort=updated&direction=asc&per_page=100`. There is no server-side `since` parameter for the pulls list endpoint — `_fetch_pulls` performs CLIENT-SIDE filtering of raw items by `updated_at >= effective_since`.
  - `issues` endpoint URL accepts server-side `since={iso}`. The issues endpoint returns PRs too — `_fetch_issues` filters out any raw item containing a `pull_request` key.
  - Bot filter: when `settings.exclude_bots` is True, items whose `author_login` is in `{dependabot[bot], renovate[bot], github-actions[bot]}` are dropped. Commits additionally drop messages starting with `Merge pull request` or `Merge branch`.
  - `pydantic.ValidationError` per-item → `_validate_items` logs a warning (`logger.warning("Skipping invalid %s item id=%s: %s", ...)`) and skips that item; others persist. Does NOT abort the run.
  - `id_field`: `"id"` for PR / Issue / ReviewComment / IssueComment; `"sha"` for Commit.
  - `_effective_since`: chooses `max(user_since, watermark_since)` when both present; either one alone otherwise; `None` when neither.
- **Edge cases observed in code:**
  - `try/except GhSubprocessError` at the `summon_all` orchestrator boundary → returns `Result(success=False, error_code="SUMMON_FETCH_FAILED")` with `error_context["returncode"]`. A failure mid-loop leaves cache files and watermarks from already-completed resources intact.
  - `try/except pydantic.ValidationError` inside `_validate_items` per-item.
  - `try/except json.JSONDecodeError` inside `read_jsonl` → raises `CacheCorruptError`.
  - Empty `items` short-circuits `append_jsonl` (returns 0, no file created).
  - `_transform_pull` / `_transform_issue` / `_transform_review_comment` / `_transform_issue_comment` return `None` (skip) when `user.login` is missing. `_transform_commit` returns `None` when `commit.author.date` is missing. `_transform_review_comment` / `_transform_issue_comment` also return `None` when the PR/issue number cannot be regex-extracted from `pull_request_url` / `issue_url`.
  - `default_branch` resolution via `gh_client.get_default_branch` runs FIRST in `summon_all`; failure → `Result(success=False, error_code=branch_result.error_code or "DEFAULT_BRANCH_FAILED")` BEFORE any fetch runs.
- **Cache / file layout:**
  - `cache_root` honours `settings.cache_dir` directly. `resolve_cache_dir(*, settings)` in `config.py` returns `os.environ["INVOCATOR_CACHE_DIR"]` if set (expanded) else `settings.cache_dir`. (Note: `cache.py` does NOT call `resolve_cache_dir` — env override path is only triggered when the CLI/caller wires it through `Settings.cache_dir`. Phase 8 will own the CLI flag plumbing.)
- **Result[T] usage:**
  - `summon_all` returns `Result[SummonStats]`. `error_code` values emitted: `SUMMON_FETCH_FAILED` (bubbled `GhSubprocessError`), or whatever `get_default_branch` returned (`REPO_NOT_FOUND`, etc.) / fallback `DEFAULT_BRANCH_FAILED`.
- **Test hooks / seams:**
  - `invocator.summon.run_gh` — patch to return crafted bytes (newline-delimited JSON objects, one per line, OR empty bytes).
  - `invocator.summon.get_default_branch` — patch to return `Result[str](success=True, data="main")` for the happy path.
  - `invocator.cache.*` functions are module-level — drive them with `tmp_path`.
  - `invocator.summon.console` is module-level (Rich); CliRunner not needed since `summon_all` is invoked directly (no Typer wrapper).
  - For watermark timestamp determinism, use `freezegun.freeze_time("2026-05-25T12:00:00Z")` to pin `datetime.now(timezone.utc)` used by `update_resource_watermark` and `summon_all`'s `started_at`/`finished_at`.
  - For bot-filter assertions: inject a raw `user.login == "dependabot[bot]"` item; after `_fetch_*`, read the resource jsonl back via `read_jsonl` and assert it's absent.
  - For pulls client-side `since` filter: include both pre- and post-watermark items in the mock response; only post-watermark items should be persisted.
- **Not yet implemented (referenced by todo):**
  - Rich `Progress` bar widget per resource: current code uses plain `console.print` lines (`[cyan]Fetching X...[/cyan]` then `[green]✓[/green] Fetched N`), not a live progress bar.
  - The `--cache-dir` CLI flag itself does not exist yet; only the env-var override path (`resolve_cache_dir`) is wired. CLI flag wiring is a Phase 8 concern.

### Tests

**Target file(s):** `tests/test_cache.py`, `tests/test_summon.py`, `tests/test_models.py` (extended)

**Cases to cover:**

For `tests/test_cache.py`:
- [x] happy: `read_jsonl(missing_path)` returns `[]`
- [x] happy: `append_jsonl(path=p, items=[{"id":1},{"id":2}])` writes 2 lines; round-trips via `read_jsonl`
- [x] happy: `append_jsonl(items=[])` is a no-op (returns 0, file not created)
- [x] happy: `merge_by_id` first call → `(N, 0)` and rows persisted
- [x] happy: `merge_by_id` second call with overlap → counts split correctly between added/updated
- [x] edge: `merge_by_id` preserves insertion order for existing rows
- [x] error: `read_jsonl` on file with one corrupt line raises `CacheCorruptError(path, line_number=2, ...)`
- [x] happy: `load_watermark(missing)` returns `{}`
- [x] happy: `save_watermark` + `load_watermark` round-trip a dict
- [x] happy: `update_resource_watermark` sets `per_resource[resource]` and refreshes `last_run_utc`; second call updates only the targeted resource
- [x] edge: atomic write — patched `os.replace` is called with a `.tmp` src and the final `dst`
- [x] edge: ISO8601 watermark values end with `Z` and never contain `+00:00`

For `tests/test_summon.py`:
- [x] happy: `summon_all` with all five resources returning empty bytes → `Result.success=True`, `SummonStats` all-zero, watermarks set for all 5 resources
- [x] happy: `summon_all` populates `pulls.jsonl` with the validated row from the mocked `gh api` response
- [x] happy: bot filter — `user.login == "dependabot[bot]"` row is not persisted; non-bot row is
- [x] happy: merge-commit drop — commit whose message starts with `Merge pull request` is filtered out; `feat:` commit persists
- [x] edge: `issues` endpoint mock returns one item with `pull_request` key → that one is filtered out
- [x] edge: `pulls` client-side `since` filter — pre-seeded watermark drops items with `updated_at` before it
- [x] edge: `pydantic.ValidationError` on one item (bad `created_at`) → skipped; other items persist; run still succeeds
- [x] error: `run_gh` raises `GhSubprocessError` on issues → `Result(success=False, error_code="SUMMON_FETCH_FAILED")`; pulls cache from earlier success is still on disk
- [x] edge: watermark intermediate state — after `_fetch_pulls` succeeds and `_fetch_issues` fails, `per_resource["pulls"]` is set but `per_resource["issues"]` is absent

For `tests/test_models.py`:
- [x] happy: `SummonStats` round-trips with all-zero counts (model_dump → model rebuild equal)
- [x] happy: `PullRequest` accepts `id: int`
- [x] happy: `Issue` accepts `id: int`

---

## Phase 6 — Transmute internals (classify) [~]

- [x] `src/invocator/classify.py` — `classify(*, cache_dir, repo) -> Result[ClassifiedStats]`. Reads cached JSONL, writes `classified/<category>.jsonl`.
- [x] `src/invocator/rules/conventional.py` — regex on conventional commit prefixes; maps to `Category`.
- [x] `src/invocator/rules/review_cues.py` — regex on imperative cues (`always/never/must/should/avoid/prefer`) and bug-pattern cues (`regress/race condition/deadlock/leak`); extracts one-sentence snippet window.
- [~] `src/invocator/rules/labels.py` — default label → category map; overridable via `[tool.invocator.labels]` in `pyproject.toml` of the **invocator project itself** (the tool's own defaults), and via `--labels-config PATH` flag for end-user overrides. (Default map implemented; `--labels-config` flag + pyproject override explicitly deferred.)
- [x] `src/invocator/rules/adr.py` — detect ADR-style PR bodies (`## Context`/`## Decision`/`## Consequences` ≥ 2 of 4) and `ADR-` title prefix.
- [x] Glossary mining: count capitalized multi-word phrases and backticked terms across titles+labels; threshold ≥3 occurrences.
- [x] Dedupe: SHA1 of normalized snippet → drop exact dupes per category.
- [x] Top-K cap: sort by `weight` desc, keep top `--top-k` (default 500) per category.

### Implementation Notes

- **Files:** `src/invocator/classify.py`, `src/invocator/rules/__init__.py`, `src/invocator/rules/conventional.py`, `src/invocator/rules/review_cues.py`, `src/invocator/rules/labels.py`, `src/invocator/rules/adr.py`, `src/invocator/models.py:101-110`
- **Public entry points:** `classify(*, settings, repo, top_k=None) -> Result[ClassifyStats]`, `classify_item(*, item, item_type) -> list[ClassifiedItem]`, `mine_glossary(*, settings, repo) -> list[ClassifiedItem]`; per-rule: `conventional.parse_conventional(*, title)`, `conventional.classify_conventional(*, title, source_ref)`, `review_cues.classify_review_cues(*, body, source_ref)`, `labels.classify_labels(*, labels, source_ref, title)`, `labels.DEFAULT_LABEL_MAP`, `adr.classify_adr(*, title, body, source_ref)`.
- **Key behaviors / invariants:**
  - Conventional commit regex: `^(feat|fix|refactor|perf|docs|test|chore|build|ci|revert)(\([^)]+\))?!?:` (`re.IGNORECASE`). `parse_conventional` returns `(type_lower, scope_inside_parens_or_empty_string)` — scope token is `""` when absent, never `None`.
  - Conventional type → category map (only these types emit items): `fix`/`revert` → `PREVENCOES`, `refactor`/`perf` → `PATTERNS`. `feat`, `docs`, `test`, `chore`, `build`, `ci` parse but produce zero items.
  - Review cue patterns: imperatives (`always|never|must|should|don'?t|avoid|prefer|do not`) → `RULES`; bug-pattern cues (`regress(ion)?|race condition|deadlock|memory leak|leak`) → `PREVENCOES`.
  - Default label → category map (in `DEFAULT_LABEL_MAP`): `bug`/`regression`→`PREVENCOES`; `architecture`/`adr`/`decision`/`rfc`→`DECISIONS`; `refactor`/`tech-debt`/`pattern`→`PATTERNS`; `convention`/`style`/`lint`→`RULES`; `domain`/`glossary`→`GLOSSARY`. Label lookup is lowercased.
  - ADR detection: ≥2 of 4 section headers (`## context`, `## decision`, `## consequences`, `## alternatives`, case-insensitive, MULTILINE) OR title prefix matching `^\s*adr-` (case-insensitive). Either condition alone is sufficient.
  - Glossary threshold: term must appear `≥ 3` times across pulls.jsonl + issues.jsonl (titles and label strings) to be emitted; weight = raw count; `source_ref = "corpus"`; signal `glossary:freq`.
  - Weight defaults: conventional=2, review cue=3 (both imperatives and bug patterns), label=1, ADR=5, glossary=raw count.
  - Snippet normalization (for dedupe hash): `re.sub(r"\s+", " ", s.strip().lower())`.
  - SHA1 dedupe per-category: `hashlib.sha1(normalized.encode("utf-8")).hexdigest()`; first occurrence wins, later dupes counted in `dropped_dupes`.
  - Top-K sort: stable `sorted(..., key=lambda it: it.weight, reverse=True)[:top_k]`; only triggered when bucket size > top_k. Default top_k comes from `settings.top_k_per_category` (500) when not passed.
  - Atomic rewrite per category: write to `classified/<cat>.jsonl.tmp` then `os.replace(tmp_path, path)`. Output dir is `cache_dir / "classified"`, created with `mkdir(parents=True, exist_ok=True)`. One file per category, always written (even when empty).
  - Deterministic: same cache contents → same output bytes (rule application is pure regex + dict lookup over deterministic JSONL read order; dedupe preserves first-seen ordering then stable sort).
- **Edge cases observed in code:**
  - `classify_review_cues(body=None, ...)` → returns `[]` immediately (also for empty string via `if not body`).
  - Code-fence stripping: `_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)` runs BEFORE regex match — text inside triple-backtick fences cannot produce review-cue hits.
  - Sentence extraction caps at 240 chars (`_SNIPPET_MAX_CHARS`); right-stripped after truncation.
  - `classify_labels` snippet falls back to `"<no title>"` when title is empty/whitespace-only.
  - `classify_adr` snippet falls back to `"<no title>"` when title is missing AND match was from body sections.
  - `mine_glossary` skips empty terms and empty/None labels; backtick regex requires 2–80 chars between backticks; capitalized phrase regex requires ≥2 capitalized words separated by whitespace.
  - `classify_item` returns `[]` for unknown `item_type`.
- **Result[T] usage:** `classify` returns `Result[ClassifyStats]`; on success `data=ClassifyStats(...)`. Any uncaught exception is converted to `Result(success=False, error_code="CLASSIFY_FAILED", error_message=str(exc))` and logged via `logger.exception`. Per-rule functions raise on bad input (pure functions, no `Result` wrapping).
- **Test hooks / seams:**
  - All rule functions (`classify_conventional`, `classify_review_cues`, `classify_labels`, `classify_adr`, `parse_conventional`) take pure inputs (`str`, `list[str]`, `str | None`) — unit-testable directly without monkeypatch.
  - `classify(*, settings, repo)` reads from `repo_cache_dir(settings=settings, repo=repo)` — populate a `tmp_path` cache (write `pulls.jsonl`, `issues.jsonl`, `commits.jsonl`, optionally `pr_review_comments.jsonl` / `issue_comments.jsonl`) and call directly with `Settings(cache_dir=tmp_path)`.
  - `mine_glossary` reads only `pulls.jsonl` and `issues.jsonl` from the repo cache dir.
  - To assert atomic write, `monkeypatch.setattr("os.replace", spy)` or patch `invocator.classify.os.replace`; `_write_bucket` calls it once per category file (5 calls per full `classify()`).
- **Not yet implemented (referenced by todo):**
  - `--labels-config PATH` CLI flag for end-user label overrides.
  - `[tool.invocator.labels]` pyproject.toml override for the tool's own defaults.

### Tests

**Target file(s):** `tests/test_classify.py`, `tests/rules/test_conventional.py`, `tests/rules/test_review_cues.py`, `tests/rules/test_labels.py`, `tests/rules/test_adr.py`, `tests/test_models.py` (extended)

**Cases to cover:**

For `tests/rules/test_conventional.py`:
- [x] happy: `parse_conventional(title="feat: add login")` returns `("feat", "")`
- [x] happy: `parse_conventional(title="fix(auth): expired token")` returns `("fix", "auth")`
- [x] happy: case-insensitive — `parse_conventional(title="FEAT: x")` returns `("feat", "")`
- [x] happy: breaking marker — `parse_conventional(title="feat!: x")` returns `("feat", "")`
- [x] edge: no match — `parse_conventional(title="random title")` returns `None`
- [x] happy: `classify_conventional(title="fix: race", source_ref="PR#1")` → 1 `ClassifiedItem(category=PREVENCOES, weight=2)`
- [x] happy: `classify_conventional(title="refactor: extract module", source_ref="PR#2")` → category=`PATTERNS`
- [x] happy: `feat:` produces no items (no automatic category)

For `tests/rules/test_review_cues.py`:
- [x] happy: body `"Always validate input"` → 1 item `RULES`, weight=3, snippet contains "always"
- [x] happy: body `"never use _id directly"` → 1 item `RULES`
- [x] happy: body `"This caused a race condition in prod"` → 1 item `PREVENCOES`, weight=3
- [x] edge: code fence with `never` inside ``` ``` ``` produces no match
- [x] edge: body `None` → returns `[]`
- [x] edge: multiple matches in one body → multiple items
- [x] edge: sentence extraction caps at 240 chars

For `tests/rules/test_labels.py`:
- [x] happy: `classify_labels(labels=["bug"], source_ref="PR#1", title="x")` → 1 item `PREVENCOES`, weight=1
- [x] happy: `classify_labels(labels=["bug", "convention"], ...)` → 2 items (PREVENCOES + RULES)
- [x] happy: case-insensitive — `labels=["BUG"]` works
- [x] edge: unknown label → no item
- [x] edge: empty title → snippet falls back to placeholder `"<no title>"`

For `tests/rules/test_adr.py`:
- [x] happy: title `"ADR-001: choose Postgres"` → 1 item `DECISIONS`, weight=5
- [x] happy: body with `## Context\n...\n## Decision\n...` (2 sections) → 1 item `DECISIONS`
- [x] happy: body with all 4 ADR sections → 1 item `DECISIONS`
- [x] edge: body with only `## Context` (1 section) → no item
- [x] edge: body `None` and title non-ADR → no item
- [x] edge: case-insensitive section headers (`## context` matches like `## Context`)

For `tests/test_classify.py` (orchestrator):
- [x] happy: populated `tmp_path` cache (3 PRs, 1 issue, 1 commit) → `ClassifyStats` with non-zero per-category counts; all 5 `classified/{cat}.jsonl` files exist
- [x] edge: dedupe — 2 identical `fix: race` PRs → only 1 entry in `prevencoes.jsonl`; `dropped_dupes >= 1`
- [x] edge: top-k cap — 600 items targeting RULES, `top_k=100` → `rules.jsonl` has 100 lines; `dropped_top_k == 500`
- [x] edge: glossary threshold — `` `fooBar` `` mentioned 4 times across PRs/issues → glossary entry with snippet `fooBar`, weight ≥ 3
- [x] happy: rerunning `classify` is idempotent — identical output files byte-for-byte
- [x] happy: atomic output — patched `os.replace` is called once per category file

For `tests/test_models.py`:
- [x] happy: `ClassifyStats` round-trips with all-zero fields

---

## Phase 7 — Inscribe internals (LLM synthesis) [x]

- [x] `src/invocator/synthesize.py` — `synthesize_all(*, settings, repo, model, dry_run, force) -> Result[SynthesisStats]`. Internal.
- [x] `src/invocator/prompts.py` — five category prompts (`RULES`, `PREVENCOES`, `PATTERNS`, `DECISIONS`, `GLOSSARY`) + `INDEX` prompt. Each is a constant string template.
- [x] One Anthropic call per category. INDEX.md is rendered deterministically (no LLM). Each call uses message blocks: system (cached `ephemeral`), corpus bundle (cached `ephemeral`), instruction (uncached).
- [x] `count_tokens_estimate(*, system, corpus) -> int` via `client.messages.count_tokens(...)`; categories above 200k tokens are skipped (per-category) unless `--force`.
- [x] `log_usage(*, response, category)` — reads `response.usage`, computes USD cost from model pricing table, logs via Rich.
- [x] Synthesis cache: SHA256 of corpus stored at `learnings/.cache/<category>.hash`. Hash match + md present → skip LLM. Mismatch → call LLM, write both `.md` and `.hash`.
- [x] `--dry-run` skips Anthropic; writes raw bullet dumps of classified snippets to `learnings/<category>.md` for inspection.
- [x] Render `learnings/INDEX.md` with repo, run timestamp, per-file bullet count, model, total cost, cached/synthesized split.

### Implementation Notes

- **Files:** `src/invocator/synthesize.py`, `src/invocator/prompts.py`, `src/invocator/models.py:120-141`, `src/invocator/models.py:84-88`
- **Public entry points:** `synthesize_all(*, settings, repo, model, dry_run=False, force=False) -> Result[SynthesisStats]`, `synthesize_category(*, client, model, category, corpus, instruction) -> Result[SynthesisOutput]`, `build_corpus(*, classified_items) -> str`, `count_tokens_estimate(*, system, corpus) -> int`, `log_usage(*, response, category, model="claude-sonnet-4-6") -> int`, `_get_client(*, api_key) -> Anthropic` (test seam)
- **Key behaviors / invariants:**
  - One Anthropic `messages.create` call per category (5 total). INDEX.md is **deterministic** (no LLM call) — rendered by `_render_index_markdown` from local counts/timestamps.
  - Prompt caching: `system` is a list with one text block carrying `cache_control={"type":"ephemeral"}`. `messages[0].content` is a list of two blocks — block[0] = corpus with `cache_control={"type":"ephemeral"}`; block[1] = instruction (NO `cache_control`).
  - `temperature=0`, `max_tokens=_MAX_OUTPUT_TOKENS=8000`.
  - Hash cache: SHA256 (hex) of corpus string at `{settings.out_dir}/.cache/{category.value}.hash`. Skip LLM only when `not force` AND `stored_hash == bundle_hash` AND `md_path.exists()`. Cached hit increments `stats.categories_cached` and re-counts bullets from existing md.
  - `--dry-run`: skips Anthropic entirely; never constructs a client. Writes `_render_dry_run_markdown` bullet dump per category; increments `categories_synthesized`. Always writes INDEX.md last.
  - Pre-flight token check: `count_tokens_estimate(...) > 200_000` (`_TOKEN_SOFT_CAP`) AND `not force` → that single category is skipped with a `[yellow]` warning; the loop continues. No special error_code is bubbled; the category simply does not get an `.md` write nor a `.hash`.
  - API key never appears in stdout/stderr/logs — the only log lines are the per-category usage line (tokens + cost) and the `cached`/skip messages.
  - Cost calculation (`_compute_cost_usd_cents`): `input_tokens * input_rate + cache_creation_tokens * input_rate * 1.25 + cache_read_tokens * input_rate * 0.10 + output_tokens * output_rate`, then `// 1_000_000` (rates are cents per million).
  - Per-item corpus serialization: `[#i] source=<ref> snippet="<escaped>" signals=[a,b]`. Escape doubles backslashes then escapes embedded double-quotes (`_escape_snippet`).
- **Edge cases observed in code:**
  - `count_tokens_estimate` only calls the SDK when `ANTHROPIC_API_KEY` env is set; falls back to `(len(system)+len(corpus))//4` on `AttributeError`, `anthropic.APIError`, or any other `Exception` (BLE001 acknowledged).
  - `_get_usage_field` / `_extract_markdown` use `getattr` on Anthropic SDK objects (Rule 9 — external dynamic data).
  - `SynthesisStats` per-category cost fields are named `<category>_cost_usd_cents` (e.g. `rules_cost_usd_cents`); `_set_cost_field` dispatches on the enum.
  - `synthesize_category` returns `Result(success=False, error_code="ANTHROPIC_API_ERROR")` on `anthropic.APIError`. In `synthesize_all`, the per-category failure is **logged and skipped** — the overall run still returns `Result(success=True)` with whichever categories succeeded reflected in `stats`. No `error_code="SYNTHESIS_FAILED"` is emitted at the orchestrator level.
  - `load_api_key` is imported lazily inside `synthesize_all` (under `if not dry_run`); when it returns `success=False`, the run returns the same `error_code` (`NO_API_KEY` / `CONFIG_READ_FAILED` / `CONFIG_PARSE_FAILED`) plus `data=None`.
  - `_load_classified` reads `{cache_dir}/{owner}__{name}/classified/{category}.jsonl`; missing file → `read_jsonl` returns `[]` → category produces empty markdown.
  - INDEX.md timestamp uses `_utc_now()` with ISO8601 `Z` suffix.
- **Result[T] usage:** error codes emitted: `NO_API_KEY` (from `load_api_key` propagation), `ANTHROPIC_API_ERROR` (per-category, swallowed by orchestrator). `CORPUS_TOO_LARGE` is NOT an error_code in this implementation — over-cap categories are skipped silently via a Rich warning. `SYNTHESIS_FAILED` likewise not present.
- **Test hooks / seams:**
  - `invocator.synthesize._get_client(*, api_key)` — patch to inject a Fake Anthropic client (records `messages.create` calls, returns canned responses).
  - `invocator.synthesize.load_api_key` is imported lazily INSIDE `synthesize_all` from `invocator.config`. Patch `invocator.config.load_api_key` to control the key path; OR set `ANTHROPIC_API_KEY` env via `monkeypatch.setenv`.
  - `invocator.synthesize.count_tokens_estimate` — patch to return a controlled count to drive the >200k branch.
  - Hash cache lives under `settings.out_dir / ".cache" / "<cat>.hash"`; use `Settings(out_dir=tmp_path / "learnings", cache_dir=tmp_path / "cache")`.
  - `invocator.synthesize.err_console` / `console` are module-level — patch if asserting on logs (or rely on captured stdout/stderr).
  - `freezegun.freeze_time` pins `_utc_now()` for deterministic INDEX.md timestamps.
- **Not yet implemented (referenced by todo):**
  - None — every Phase 7 sub-item is implemented. Divergence from the original todo wording: there is no Anthropic call for INDEX.md (deliberate; the file is rendered locally), and the over-cap branch is silent rather than returning `error_code=CORPUS_TOO_LARGE`.

### Tests

**Target file(s):** `tests/test_synthesize.py` (mirror `src/invocator/synthesize.py`)

**Cases to cover:**

For `build_corpus`:
- [x] happy: empty list → returns empty string
- [x] happy: 3 items → output contains each `source_ref` and `snippet`; embedded `"` is escaped to `\"`

For `count_tokens_estimate`:
- [x] edge: no `ANTHROPIC_API_KEY` env → falls back to `(len(system)+len(corpus))//4`
- [x] edge: SDK `count_tokens` raises `AttributeError` → falls back to local estimate
- [x] happy: fake `_get_client` returning client whose `messages.count_tokens` returns `input_tokens=12345` → returns 12345

For `log_usage`:
- [x] happy: response with all usage fields → returns non-negative cost
- [x] edge: response missing `cache_creation_input_tokens` / `cache_read_input_tokens` (None) → defaults to 0, no exception

For `synthesize_category`:
- [x] happy: fake client returns markdown response → `Result.success=True`, `SynthesisOutput` populated with usage fields
- [x] happy: request payload sent to `client.messages.create` — `system` is a list with one block carrying `cache_control={"type":"ephemeral"}`; user content has corpus (with cache_control) + instruction (without)
- [x] error: `anthropic.APIError` raised by client → `Result(success=False, error_code="ANTHROPIC_API_ERROR")`, `error_context.category` set

For `synthesize_all`:
- [x] happy `dry_run=True`: `_get_client` NOT called; all 5 `.md` files written; INDEX.md written; each `.md` is the dry-run bullet dump format
- [x] happy `dry_run=False` with fake client and classified buckets present: 5 category `.md` written, 5 `.hash` files written, INDEX.md written with cost totals
- [x] happy hash cache hit: second call with identical corpus → fake client `messages.create` NOT invoked for that category; `categories_cached` increments; `.md` unchanged
- [x] happy hash cache miss: modify one classified item → that category re-synthesizes; other 4 stay cached
- [x] error: no API key (not dry_run) — patch `invocator.config.load_api_key` to return `Result(success=False, error_code="NO_API_KEY")` → `synthesize_all` returns the same
- [x] happy: INDEX.md contains repo name, model, total cost, cached/5 ratio, per-file counts
- <!-- divergence: classified dir absent does NOT return CLASSIFY_OUTPUT_MISSING; code produces empty md. Covered indirectly by dry-run-with-empty-cache test. -->
- <!-- divergence: corpus > 200k + force=False is a silent skip (warning), not Result error_code=CORPUS_TOO_LARGE. -->
- [x] edge: pre-flight token estimate > 200_000 + `force=False` → category is skipped (no `messages.create` call for it, no `.md`/`.hash` written for it)
- [x] edge: pre-flight token estimate > 200_000 + `force=True` → category proceeds (client called)

For `SynthesisOutput` / `SynthesisStats`:
- [x] happy: round-trip both models

---

## Phase 8 — `extract wisdom` (the full ritual) [x]

- [x] `src/invocator/commands/extract.py` — Typer sub-app with `wisdom` subcommand. Args: `--repo` (required), `--since`, `--out` (default `./learnings`), `--cache-dir`, `--model` (default `claude-sonnet-4-6`), `--top-k 500`, `--dry-run`, `--yes` (skip cost confirmation), `--force-refetch`.
- [x] Pipeline: `forge`-check (Result error if no API key and not `--dry-run`) → `gh_client.check_installed + check_auth` → `summon_all` → `classify` → `synthesize_all`.
- [x] Before `summon_all`: run the same probe as `scry cost`, print the table, **prompt for confirmation** unless `--yes`. On "no", exit 0 with `Aborted by user`.
- [x] Any step returning `Result(success=False)` aborts the run with the right exit code and Rich error panel; preceding successful steps' cache is preserved (re-run is cheap).
- [x] Final Rich summary: where the `learnings/` files were written, how many entries per file, total $ spent.
- [x] E2E smoke target: `invocator extract wisdom --repo OleveCo/CourseGPTBackend --dry-run --top-k 50` completes without network calls beyond `gh api`, produces 5 files + INDEX in `./learnings/`.

### Implementation Notes

- **Files:** `src/invocator/commands/extract.py` (new), `src/invocator/cli.py` (modified — `extract` group now imports from `commands/extract.py` instead of an inline stub), `src/invocator/commands/scry.py` (modified — extracted shared `render_cost_preview(*, repo, default_branch, model, since)` helper consumed by both `scry cost` (non-`--json` mode) and `extract wisdom`).
- **Public entry points:** `invocator extract wisdom`; `extract.extract_wisdom(...)` Typer command; reusable `scry.render_cost_preview(*, repo, default_branch, model, since)`; helpers `extract._parse_since`, `extract._clear_watermark`, `extract._count_bullets`, `extract._exit_code_for`, `extract._abort`.
- **Key behaviors / invariants:**
  - Pipeline order: pre-checks (`check_gh_installed` → `check_auth` → `parse_repo` → optional `load_api_key` → `get_default_branch`) → cost preview + confirm → `summon_all` → `classify` → `synthesize_all` → final summary.
  - Pre-checks (exit 2 on failure) include: `GH_NOT_INSTALLED`, `GH_NOT_AUTHENTICATED`, `INVALID_REPO`, `REPO_NOT_FOUND`, `NO_API_KEY`, `CONFIG_READ_FAILED`, `CONFIG_PARSE_FAILED`. Defined as a module-level `frozenset` constant `_PRECHECK_ERROR_CODES`.
  - Cost preview reuses scry's probe logic via `render_cost_preview` (which probes all 5 endpoints and prints a Rich table + summary line). `--yes` skips the `typer.confirm` call entirely.
  - Mid-run failures (summon / classify / synthesize) exit 1 — earlier-step cache (jsonl + watermark) remains intact because each step writes atomically before returning.
  - `--force-refetch` deletes `{cache_dir}/{owner}__{name}/watermark.json` before summon if it exists; uses `Path.unlink()`.
  - `--since YYYY-MM-DD` parsed to UTC midnight via `datetime.strptime(..., "%Y-%m-%d").replace(tzinfo=timezone.utc)`; passed as `since=` to `summon_all` (and forwarded as string to `render_cost_preview` for display only).
  - Exit code mapping is documented in module-level constants (`_EXIT_SUCCESS=0`, `_EXIT_MID_RUN=1`, `_EXIT_PRECHECK=2`) and routed via `_exit_code_for(error_code=...)` membership check in `_PRECHECK_ERROR_CODES`.
  - Final summary: prints "Done." then per-category bullet count from `out/<cat>.md` via `_count_bullets` (lines beginning with `- ` or `* ` after `lstrip`); references INDEX.md; reports `categories_synthesized`, `categories_cached`, total dollars (`synth_stats.total_cost_usd_cents / 100` formatted `${:.2f}`).
- **Edge cases:**
  - `--dry-run` skips `load_api_key` entirely (the key check block is guarded by `if not dry_run:`); `synthesize_all` is called with `dry_run=True` and never hits Anthropic.
  - Aborted confirmation (`typer.confirm` → False) prints `[yellow]Aborted by user.[/yellow]` and exits 0 (`_EXIT_SUCCESS`); `summon_all` is never called.
  - `_abort` falls back to `fallback_code` only when `result.error_code is None`; otherwise `_exit_code_for` membership determines exit 2 vs exit 1.
  - `Result.error_code` for the API-key branch is mapped through the same precheck set (`NO_API_KEY` etc.); the panel includes a "Run: invocator forge key" hint.
- **Result[T] usage:** every step checks `.success` (and `.data is not None` for typed payloads). Precheck codes → exit 2 via `_PRECHECK_ERROR_CODES`; mid-run failures with non-precheck codes → exit 1 via `_exit_code_for` default.
- **Test hooks / seams:**
  - All collaborators are imported at module level in `invocator.commands.extract`, so tests patch by name: `check_gh_installed`, `check_auth`, `parse_repo`, `get_default_branch`, `load_api_key`, `summon_all`, `classify`, `synthesize_all`, `render_cost_preview`, and `typer.confirm` (patch the symbol on the `typer` module from extract's POV: `invocator.commands.extract.typer.confirm`).
  - For `--dry-run` happy-path tests, just wire `synthesize_all` to actually write to the `out` directory (or assert on `call_args`); no Anthropic stub needed because dry-run skips the API key entirely.
  - `console` and `err_console` are module-level in `extract.py`; CliRunner captures their output via stdout/stderr.
  - `_clear_watermark` can be exercised by pre-seeding `tmp_path / "{owner}__{name}/watermark.json"` and asserting it's gone after invocation with `--force-refetch`.

### Tests

**Target file(s):** `tests/commands/test_extract.py` (new), `tests/test_cli_smoke.py` (existing `test_extract_wisdom_stub` rewritten to match new contract).

**Cases to cover:**

Pipeline happy path:
- [x] happy `--dry-run`: all dependencies patched to success-Results; fake `synthesize_all` writes 5 `<category>.md` + INDEX.md to `out`; exit 0; summary printed
- [x] happy without `--dry-run`: `load_api_key` returns success; `synthesize_all` called with `dry_run=False`
- [x] happy `--yes`: `typer.confirm` NOT called (call_count == 0)
- [x] happy explicit confirm (no `--yes`, user says yes): `typer.confirm` returns True → pipeline proceeds (summon called)

Pre-check exits:
- [x] error: `check_gh_installed` failed → exit 2, `summon_all` not called
- [x] error: `check_auth` failed → exit 2
- [x] error: `parse_repo` failed (invalid input) → exit 2
- [x] error: `get_default_branch` returns `REPO_NOT_FOUND` → exit 2
- [x] error: `load_api_key` failed AND not `--dry-run` → exit 2; message mentions `invocator forge key`
- [x] happy: `--dry-run` skips API key check entirely (patch `load_api_key` to failed; pipeline still proceeds because dry_run=True)

User abort:
- [x] happy: `typer.confirm` returns False → exit 0; `summon_all` NOT called; "Aborted" message printed

Mid-run failures (exit 1):
- [x] error: `summon_all` failed → exit 1; `classify` NOT called
- [x] error: `classify` failed → exit 1; `synthesize_all` NOT called
- [x] error: `synthesize_all` failed → exit 1

Flag plumbing:
- [x] happy: `--force-refetch` deletes pre-seeded `watermark.json` before summon
- [x] happy: `--since 2024-01-01` parsed to UTC midnight `datetime` and passed into `summon_all(since=...)`
- [x] happy: `--top-k 100` propagates: `classify(..., top_k=100)`
- [x] happy: `--model claude-opus-4-7` propagates to `synthesize_all` and `render_cost_preview`
- [x] happy: `--cache-dir /tmp/foo` reflected in `Settings.cache_dir` for summon/classify/synthesize
- [x] happy: `--out /tmp/bar` reflected in `Settings.out_dir`

Settings construction:
- [x] happy: `Settings` built from CLI args has `top_k_per_category` = `--top-k` value, `model` = `--model` value

Final summary:
- [x] happy: dry-run summary mentions the 5 file paths under `out` and `INDEX.md`
- [x] happy: non-dry-run path summary contains a `$` cost value

CLI smoke (`tests/test_cli_smoke.py`):
- [x] update: `extract wisdom` with no `--repo` exits 2; `extract wisdom --help` exits 0 and contains "wisdom" plus all 9 flag names

---

## Phase 9 — Distribution [~]

- [x] `README.md` real content: install (`pipx install invocator`), prerequisites (`gh auth login`), quickstart (3 spells), troubleshooting.
- [x] `CHANGELOG.md` — `0.1.0` entry.
- [x] `.github/workflows/ci.yml` — runs `black --check`, `isort --check-only`, `flake8`, `pyright`, `pytest` on push/PR. Matrix: Python 3.11, 3.12.
- [x] `.github/workflows/release.yml` — triggers on tag `v*`: `uv build` (or `python -m build`), `twine upload` to PyPI using `${{ secrets.PYPI_TOKEN }}`, attach wheel to GitHub Release.
- [x] Pre-publish dry run: `python -m build && twine check dist/*`. Verify `gh-extractor` is not the name conflicting with `invocator` on PyPI (search PyPI before first publish).
- [ ] Tag `v0.1.0`, run release workflow, confirm `pipx install invocator` works on a clean machine. (Deferred — PyPI publish blocked pending user authorization; see Implementation Notes.)

### Implementation Notes

- **Files:** `README.md`, `CHANGELOG.md`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml`
- **Public entry points / artifacts:**
  - `README.md` — user-facing install / quickstart / troubleshooting prose.
  - `CHANGELOG.md` — Keep-a-Changelog format with `[Unreleased]` and `[0.1.0]` sections; 0.1.0 still marked UNRELEASED until a real PyPI publish.
  - `.github/workflows/ci.yml` — runs on push + PR to `main`; matrix Python 3.11 / 3.12 / 3.13; steps: `black --check`, `isort --check-only`, `flake8`, `pyright`, `pytest`.
  - `.github/workflows/release.yml` — triggered on tag push `v*`; builds (`python -m build`), runs `twine check`, `twine upload` (uses `PYPI_API_TOKEN` repo secret), and `gh release create` with the built artifacts attached.
  - `pyproject.toml` — `version = "0.1.0"`; `[project.scripts] invocator = "invocator.cli:app"`; `[build-system]` = hatchling; `[project.optional-dependencies].dev` consolidated to `pytest`, `pytest-mock`, `freezegun`, `black`, `isort`, `flake8`, `pyright` (ruff dropped); `[tool.hatch.build.targets.wheel] packages = ["src/invocator"]`.
- **Key invariants:**
  - PyPI name `invocator` is available (HTTP 404 on `https://pypi.org/pypi/invocator/json`).
  - `twine check` PASSED on both sdist and wheel; `dist/` was cleaned after the dry run.
  - Build artifacts are deterministic from the source tree (hatchling).
  - CI matrix covers Python 3.11+ (the project's declared minimum).
  - The release workflow requires `PYPI_API_TOKEN` repository secret to be set in GitHub repo settings before first publish.
- **Edge cases:**
  - Pre-existing pyright "pyproject parse" warning is benign — does not affect typecheck (0 errors).
  - User-modified README (linter-style cleanup) was preserved; substance still matches the spec.
- **Deferred (cannot complete without explicit user authorization):**
  - `git tag v0.1.0 && git push --tags` — would trigger the release workflow → `twine upload` to real PyPI. The auto-mode classifier previously denied this. Will fire when the user explicitly authorizes a publish.
  - Verifying `pipx install invocator` on a clean machine — depends on the publish completing.
- **Result[T] usage:** none (no Python code added in this phase).
- **Test hooks / seams:** none (no new code; workflows and docs are not unit-tested).

### Tests

<!-- No tests in this phase — distribution is docs + CI config; no Python source changed. -->
