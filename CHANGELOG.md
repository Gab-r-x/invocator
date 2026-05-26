# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.5] — 2026-05-26

### Fixed
- `decisions` (and any other category with 0 classified items) used to
  abort synthesis with `Error code: 400 - cache_control cannot be set
  for empty text blocks`. Now the LLM call is skipped for empty
  categories and a friendly placeholder is written to the `.md` file.
- `_count_bullets` in `extract.py` only counted `- ` / `* ` lines, so
  categories whose template uses `### ` H3 sections (prevencoes,
  patterns, decisions) and `**Term**` lines (glossary) reported as
  `0 entries` in the terminal even when the file had real content. Now
  counts dash bullets, H3 sections, and bold-prefix lines.

### Changed
- `SynthesisStats` gains two new counters: `categories_dry_run_dumped`
  (was being conflated with `categories_synthesized`) and
  `categories_skipped_empty`. The terminal summary now shows the
  breakdown explicitly.

## [0.1.4] — 2026-05-26

### Changed
- **Classification now sends full bodies to the LLM, not 240-char windows.**
  Previously each regex hit produced a `ClassifiedItem` with a snippet of
  ~one sentence around the match. That stripped the surrounding context
  that lets the LLM judge whether a "should" is a real rule or a passing
  thought. Now: one item per (category, source_ref), `snippet` = the
  full body (or `title\n\nbody` for conventional commits / labels / ADRs),
  `signals` aggregates every cue that fired in that body.
- Long bodies are truncated to ~4000 chars via `truncate_body` with an
  explicit `[... truncated by invocator ...]` marker.

### Added
- `rules/trivial_filter.py`: drops bodies that are pure `lgtm`, `nit`,
  `+1`, emoji-only, or empty, before classification ever sees them.
- `classify_conventional`, `classify_labels`, `classify_adr` now accept
  the PR/issue/commit `body` and use it as the snippet (was title-only).
- 12 new tests covering trivial filter, full-body snippets, multi-cue
  aggregation, and over-long truncation.

### Why
PR descriptions and code-review comments are dense with intent.
Heuristics are good at routing (which category) but terrible at deciding
which 240 chars carry the meaning. Pass the whole thing; the LLM does
the consolidation in its own pass.

## [0.1.3] — 2026-05-26

### Fixed
- `summon` was passing `--paginate` as a top-level `gh` flag instead of
  as a flag of `gh api`. The invocation `gh --paginate api ...` was
  rejected by gh, breaking every real-world `extract wisdom` run with
  `SUMMON_FETCH_FAILED`. Now correctly emits `gh api --paginate ...`.
- Updated `test_run_gh_paginate_inserts_flag_after_api` to assert the
  correct arg order.

## [0.1.2] — 2026-05-25

### Added
- `invocator --version` flag — prints the installed version and exits.
- README note about `gh auth switch` for multi-account users (the repo `invocator` sees depends on `gh`'s active identity).

## [0.1.1] — 2026-05-25

### Fixed
- `scry cost` was overestimating items by 100x. `probe_endpoint` calls
  `gh api ... per_page=1` so the `Link: rel="last"` page number IS the item
  count; the previous code multiplied it by 100, producing absurd cost
  predictions (e.g. ~$92 for a repo where the real cost is ~$1).

### Tests
- Updated `test_probe_endpoint_link_last_page` to assert the corrected count.

## [0.1.0] — 2026-05-25

### Added
- Initial scaffold: `forge key`, `scry cost`, `extract wisdom`
- gh subprocess client (no direct GitHub HTTP)
- JSONL cache with per-resource watermarks
- Heuristic classification: conventional commits, review cues, labels, ADR detection, glossary mining
- LLM synthesis with prompt caching and SHA256 hash-skip
- 156 hermetic CLI integration tests
- MIT license
