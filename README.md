# invocator

> Summon the accumulated wisdom of a GitHub repository into a `learnings/` grimoire.

`invocator` is a CLI that connects to a GitHub project, extracts its PRs, issues, commits, and code-review conversations, and synthesizes that history into a folder of markdown files — rules, prevenções, patterns, decisions, glossary — so the tacit knowledge of a codebase becomes navigable documentation.

> ⚠️ **Early development.** The scaffold is being built. See [docs/todos/todo_scaffold.md](docs/todos/todo_scaffold.md) for the MVP plan.

## The three spells

```bash
invocator forge key                    # bind a pact with Anthropic (set API key)
invocator scry cost --repo owner/name  # gaze ahead: cost / time / item counts before the ritual
invocator extract wisdom --repo owner/name   # the full ritual — produces ./learnings/
```

## How it works

1. **summon** — `gh api --paginate` pulls PRs, issues, commits, and review comments into a JSONL cache.
2. **transmute** — heuristics (conventional commits, review-comment cues, labels, ADR detection) classify each item into one of five categories.
3. **inscribe** — one Anthropic call per category (with prompt caching) writes `learnings/<category>.md`. A synthesis hash cache means re-runs without deltas are free.

## Prerequisites

- Python 3.11+
- [`gh` CLI](https://cli.github.com/) authenticated (`gh auth login`) — invocator never calls `api.github.com` directly
- An Anthropic API key (set once via `invocator forge key`)

## Install

Coming soon to PyPI. For now, from source:

```bash
git clone https://github.com/Gab-r-x/invocator.git
cd invocator
pip install -e .
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

This project uses a strict phased-todo workflow. See:

- [docs/STANDARDS.md](docs/STANDARDS.md) — non-negotiable engineering rules
- [docs/todos/README.md](docs/todos/README.md) — operational contract for the executor → progress → tests pipeline
- [CLAUDE.md](CLAUDE.md) — workflow for AI-assisted contributions
