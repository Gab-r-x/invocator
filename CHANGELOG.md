# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
