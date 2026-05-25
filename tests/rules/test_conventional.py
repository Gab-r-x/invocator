from invocator.models import Category
from invocator.rules.conventional import classify_conventional, parse_conventional


def test_parse_conventional_simple_feat() -> None:
    assert parse_conventional(title="feat: add login") == ("feat", "")


def test_parse_conventional_with_scope() -> None:
    assert parse_conventional(title="fix(auth): expired token") == ("fix", "auth")


def test_parse_conventional_case_insensitive() -> None:
    assert parse_conventional(title="FEAT: x") == ("feat", "")


def test_parse_conventional_breaking_marker() -> None:
    assert parse_conventional(title="feat!: x") == ("feat", "")


def test_parse_conventional_no_match_returns_none() -> None:
    assert parse_conventional(title="random title") is None


def test_classify_conventional_fix_maps_to_prevencoes() -> None:
    items = classify_conventional(title="fix: race", source_ref="PR#1")
    assert len(items) == 1
    assert items[0].category == Category.PREVENCOES
    assert items[0].weight == 2
    assert items[0].source_ref == "PR#1"


def test_classify_conventional_refactor_maps_to_patterns() -> None:
    items = classify_conventional(title="refactor: extract module", source_ref="PR#2")
    assert len(items) == 1
    assert items[0].category == Category.PATTERNS


def test_classify_conventional_feat_produces_no_items() -> None:
    assert classify_conventional(title="feat: add new thing", source_ref="PR#3") == []
