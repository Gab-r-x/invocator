from invocator.models import Category
from invocator.rules.adr import classify_adr


def test_adr_title_prefix_detects() -> None:
    items = classify_adr(title="ADR-001: choose Postgres", body=None, source_ref="PR#1")
    assert len(items) == 1
    assert items[0].category == Category.DECISIONS
    assert items[0].weight == 5


def test_body_two_sections_detects() -> None:
    body = "## Context\nsome context\n\n## Decision\nthe decision"
    items = classify_adr(title="A normal title", body=body, source_ref="PR#2")
    assert len(items) == 1
    assert items[0].category == Category.DECISIONS


def test_body_all_four_sections_detects() -> None:
    body = "## Context\nc\n\n## Decision\nd\n\n" "## Consequences\nconseq\n\n## Alternatives\nalts"
    items = classify_adr(title="title", body=body, source_ref="PR#3")
    assert len(items) == 1
    assert items[0].category == Category.DECISIONS


def test_body_single_section_does_not_detect() -> None:
    body = "## Context\nonly context here"
    assert classify_adr(title="title", body=body, source_ref="PR#4") == []


def test_body_none_and_non_adr_title_does_not_detect() -> None:
    assert classify_adr(title="some normal title", body=None, source_ref="PR#5") == []


def test_section_headers_are_case_insensitive() -> None:
    body = "## context\nc\n\n## decision\nd"
    items = classify_adr(title="title", body=body, source_ref="PR#6")
    assert len(items) == 1
    assert items[0].category == Category.DECISIONS
