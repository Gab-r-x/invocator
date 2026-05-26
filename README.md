# invocator

> Summon the accumulated wisdom of a GitHub repository into a `learnings/` grimoire. ✨

`invocator` is a CLI that points at any GitHub repository, walks its PRs, issues, commits, and code-review conversations, and synthesizes that history into a folder of categorized markdown files — rules, prevenções, patterns, decisions, glossary — so the tacit knowledge living in a project's timeline becomes navigable documentation.

## The three spells

| Spell | What it does |
| --- | --- |
| `invocator forge key` | Bind a pact with Anthropic — store and validate your API key |
| `invocator scry cost --repo owner/name` | Gaze ahead: cost / wall time / item counts before the ritual |
| `invocator extract wisdom --repo owner/name` | The full ritual — produces `./learnings/` |

## Prerequisites

- Python **3.11+**
- [`gh` CLI](https://cli.github.com/) installed and authenticated (`gh auth login`) — invocator never calls `api.github.com` directly
- An **Anthropic API key**

> **Multi-account `gh` users:** `invocator` runs as whichever GitHub identity `gh auth status` reports as *active*. If a repo lives in an org and `REPO_NOT_FOUND` surprises you, switch with `gh auth switch` before re-running.

## Install

```bash
pipx install invocator        # recommended
# or
uv tool install invocator
# or, from source
git clone https://github.com/Gab-r-x/invocator.git && cd invocator && pip install -e .
```

## Quickstart

```bash
invocator forge key
invocator scry cost --repo OleveCo/CourseGPTBackend
invocator extract wisdom --repo OleveCo/CourseGPTBackend
```

After the ritual completes, `./learnings/` will contain six markdown files synthesized from the repo's history.

## Output structure

| File | Contents |
| --- | --- |
| `rules.md` | Conventions and imperatives ("always X", "never Y") mined from review comments |
| `prevencoes.md` | Bug patterns, regressions, and pitfalls the team has already paid for |
| `patterns.md` | Refactors and architectural patterns that recur in the codebase |
| `decisions.md` | ADR-style decisions extracted from PRs and issues |
| `glossary.md` | Domain terms and named concepts that recur ≥3 times |
| `INDEX.md` | Run metadata: repo, timestamp, model, cost, per-file bullet counts |

## How it works

1. **summon** — `gh api --paginate` pulls PRs, issues, commits, and review comments into a JSONL cache with per-resource watermarks (re-runs are incremental).
2. **transmute** — heuristics (conventional commits, review-cue regexes, labels, ADR detection, glossary mining) classify each item into one of five categories. SHA1 dedupe + top-K cap per category.
3. **inscribe** — one Anthropic call per category, with explicit prompt caching, writes `learnings/<category>.md`. A SHA256 corpus hash means re-runs without deltas are free (no LLM call). `INDEX.md` is rendered deterministically.

## Cost

Roughly **$1–3 USD** for medium-sized repos with `claude-sonnet-4-6`. Always preview with `invocator scry cost --repo X` first. Re-runs without changes are free thanks to the hash cache.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `gh: command not found` | Install gh: https://cli.github.com/ |
| `GH_NOT_AUTHENTICATED` | Run `gh auth login` |
| `NO_API_KEY` | Run `invocator forge key` |
| `CORPUS_TOO_LARGE` | Cap inputs: `--top-k 100` |
| Want to re-fetch from scratch | `invocator extract wisdom --repo X --force-refetch` |

## Contributing

This project follows a strict phased-todo workflow. Before contributing, read:

- [CLAUDE.md](CLAUDE.md) — workflow and project rules
- [docs/STANDARDS.md](docs/STANDARDS.md) — the non-negotiable engineering rules
- [docs/todos/README.md](docs/todos/README.md) — operational contract for the executor → progress → tests pipeline

## License

MIT — see [LICENSE](LICENSE).
