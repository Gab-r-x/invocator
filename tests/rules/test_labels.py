from invocator.models import Category
from invocator.rules.labels import classify_labels


def test_single_known_label_bug_maps_to_prevencoes() -> None:
    items = classify_labels(labels=["bug"], source_ref="PR#1", title="x")
    assert len(items) == 1
    assert items[0].category == Category.PREVENCOES
    assert items[0].weight == 1


def test_two_known_labels_emit_two_items() -> None:
    items = classify_labels(labels=["bug", "convention"], source_ref="PR#2", title="x")
    categories = {it.category for it in items}
    assert categories == {Category.PREVENCOES, Category.RULES}
    assert len(items) == 2


def test_label_lookup_is_case_insensitive() -> None:
    items = classify_labels(labels=["BUG"], source_ref="PR#3", title="x")
    assert len(items) == 1
    assert items[0].category == Category.PREVENCOES


def test_unknown_label_produces_no_item() -> None:
    assert classify_labels(labels=["zzz-unknown"], source_ref="PR#4", title="x") == []


def test_empty_title_falls_back_to_placeholder_snippet() -> None:
    items = classify_labels(labels=["bug"], source_ref="PR#5", title="")
    assert len(items) == 1
    assert items[0].snippet == "<no title>"
