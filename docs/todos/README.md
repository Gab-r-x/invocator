# docs/todos/ — Operational Contract

This folder owns the **plan-of-record** for every feature being shipped in `invocator`. One file per feature, lifecycle managed by three slash-command skills working together.

## File layout

```
docs/todos/
├── README.md              # this file
└── todo_<feature>.md      # one per in-flight feature (e.g. todo_scaffold.md)

docs/past/
└── YYYY-MM/
    └── todo_<feature>.md  # archived after shipping
```

A todo file is "in flight" while it lives in `docs/todos/`. The moment all phases are `[x]` and tests are green, the orchestrator moves it to `docs/past/YYYY-MM/` (current month).

## File anatomy

Every `todo_<feature>.md` is structured in **phases**, numbered and titled. Each phase contains:

1. **Sub-item checklist** — `[ ]` / `[~]` / `[x]` items the executor implements.
2. **`### Implementation Notes`** — written by `/todo-progress` after implementation. Source of truth for what was actually built. Downstream skills read this first.
3. **`### Tests`** — written by `/todo-tests` after notes exist. Plan + checklist of test cases.

Phases are separated by `---`. Phases run sequentially: phase N depends on N-1's notes existing.

Skeleton:

```markdown
# <Feature title>

## Phase 1 — <name>

- [ ] sub-item 1
- [ ] sub-item 2

### Implementation Notes
<filled by /todo-progress>

### Tests
<filled by /todo-tests>

---

## Phase 2 — <name>

- [ ] ...
```

## Lifecycle

```
   draft todo file  →  /todo-orchestrator <feature>
                              │
                              ▼
                       pick next phase
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      /todo-executor   /todo-progress   /todo-tests
      (writes src/)    (marks [x] +     (writes tests/ +
                        notes block)     tests block)
                              │
                              ▼
                    verification gates
                    (black, isort, flake8,
                     pyright, pytest, smoke)
                              │
                       all gates green?
                              │
                       yes → next phase
                       no  → loop / escalate
                              │
                       phases exhausted?
                              │
              mv docs/todos/todo_X.md → docs/past/YYYY-MM/
```

## The three skills — strict separation

| Skill | Reads | Writes | Never touches |
|---|---|---|---|
| `/todo-executor` | todo file, prior phases' `Files:` line, `src/` | `src/invocator/` | the todo's checkboxes, `tests/`, git |
| `/todo-progress` | todo file, `src/`, `git log` | the todo file (checkboxes + Notes) | `src/`, `tests/`, git |
| `/todo-tests` | todo file (Notes block is required), `src/`, `tests/fixtures/` | `tests/`, the todo file's Tests block | `src/`, git |

This separation is non-negotiable. The executor never marks `[x]` because it can't tell the difference between "I wrote the code" and "the code actually does the thing." That's why `/todo-progress` exists — it re-reads the code with fresh eyes and only marks items that have real implementation.

## Verification gates

A phase is **not done** until all of these exit 0:

```bash
black --check --line-length=100 src/ tests/
isort --check-only --profile=black src/ tests/
flake8 --max-line-length=100 src/ tests/
pyright src/
pytest tests/ -v
```

Plus, when a phase touched the CLI runtime, a smoke:

```bash
pip install -e . --quiet
invocator --help
invocator <new-spell> --help        # whatever the phase added
```

No spell that requires network/auth is exercised in the gate — `--help` is enough to prove the entrypoint wires.

## Naming conventions

- **File:** `todo_<slug>.md`, slug in `kebab-case`. Examples: `todo_scaffold.md`, `todo_distribution.md`.
- **Phase header:** `## Phase N — <Title Case Name>`. N starts at 1, monotonic.
- **Sub-items:** imperative mood, present tense. "Implement gh client" not "gh client implementation".
- **Checkbox states:**
  - `[ ]` — not started or not implemented
  - `[~]` — partial; gap recorded in Notes
  - `[x]` — implemented in code (verified by `/todo-progress`)

## When to create a new todo file

- New feature spanning 3+ phases? → new `todo_<slug>.md`.
- Bugfix or single-file change? → no todo; just do it.
- Refactor that touches 1 module? → no todo.
- Big refactor across many modules? → todo file.

When in doubt, no todo — todos are for work that needs phasing and memory across sessions.

## Archiving

When the orchestrator declares a feature shipped, it runs:

```bash
mkdir -p docs/past/$(date +%Y-%m)
mv docs/todos/todo_<feature>.md docs/past/$(date +%Y-%m)/
```

Archived todos stay as historical record — never deleted, never edited after archive. If a regression surfaces months later, the archived `Implementation Notes` are the cheapest map back to the code that owns the behavior.

## References

- [docs/STANDARDS.md](../STANDARDS.md) — non-negotiable engineering rules every phase must respect.
- [.claude/skills/todo-orchestrator/SKILL.md](../../.claude/skills/todo-orchestrator/SKILL.md)
- [.claude/skills/todo-executor/SKILL.md](../../.claude/skills/todo-executor/SKILL.md)
- [.claude/skills/todo-progress/SKILL.md](../../.claude/skills/todo-progress/SKILL.md)
- [.claude/skills/todo-tests/SKILL.md](../../.claude/skills/todo-tests/SKILL.md)
