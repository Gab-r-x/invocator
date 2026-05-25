# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
