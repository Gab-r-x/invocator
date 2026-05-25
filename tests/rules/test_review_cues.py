from invocator.models import Category
from invocator.rules.review_cues import classify_review_cues


def test_imperative_always_produces_rules_item() -> None:
    items = classify_review_cues(body="Always validate input.", source_ref="PR#1")
    assert len(items) == 1
    assert items[0].category == Category.RULES
    assert items[0].weight == 3
    assert "always" in items[0].snippet.lower()


def test_imperative_never_produces_rules_item() -> None:
    items = classify_review_cues(body="never use _id directly", source_ref="PR#2")
    assert len(items) == 1
    assert items[0].category == Category.RULES


def test_bug_pattern_race_condition_produces_prevencoes_item() -> None:
    items = classify_review_cues(body="This caused a race condition in prod.", source_ref="PR#3")
    assert len(items) == 1
    assert items[0].category == Category.PREVENCOES
    assert items[0].weight == 3


def test_code_fence_suppresses_match() -> None:
    body = "```\nnever do this in code\n```"
    assert classify_review_cues(body=body, source_ref="PR#4") == []


def test_body_none_returns_empty() -> None:
    assert classify_review_cues(body=None, source_ref="PR#5") == []


def test_multiple_matches_produce_multiple_items() -> None:
    body = "Always validate input. Never trust user data."
    items = classify_review_cues(body=body, source_ref="PR#6")
    assert len(items) == 2
    assert all(it.category == Category.RULES for it in items)


def test_sentence_extraction_caps_at_240_chars() -> None:
    # one very long sentence (no terminators) containing "always"
    long_sentence = "always " + ("x" * 500)
    items = classify_review_cues(body=long_sentence, source_ref="PR#7")
    assert len(items) == 1
    assert len(items[0].snippet) <= 240
