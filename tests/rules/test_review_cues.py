from invocator.models import Category
from invocator.rules.review_cues import classify_review_cues


def test_imperative_always_produces_rules_item() -> None:
    items = classify_review_cues(body="Always validate input.", source_ref="PR#1")
    assert len(items) == 1
    assert items[0].category == Category.RULES
    assert items[0].weight == 3
    assert "always" in items[0].snippet.lower()
    assert items[0].signals == ["cue:always"]


def test_imperative_never_produces_rules_item() -> None:
    items = classify_review_cues(body="never use _id directly", source_ref="PR#2")
    assert len(items) == 1
    assert items[0].category == Category.RULES
    assert items[0].signals == ["cue:never"]


def test_bug_pattern_race_condition_produces_prevencoes_item() -> None:
    items = classify_review_cues(body="This caused a race condition in prod.", source_ref="PR#3")
    assert len(items) == 1
    assert items[0].category == Category.PREVENCOES
    assert items[0].weight == 3
    assert "race condition" in items[0].signals[0]


def test_code_fence_suppresses_match() -> None:
    body = "```\nnever do this in code\n```"
    assert classify_review_cues(body=body, source_ref="PR#4") == []


def test_body_none_returns_empty() -> None:
    assert classify_review_cues(body=None, source_ref="PR#5") == []


def test_multiple_imperatives_collapse_to_single_item_with_aggregated_signals() -> None:
    # 0.1.4: a body with N imperatives produces ONE classified item carrying
    # the full body as snippet and all unique cues as aggregated signals.
    # The LLM does the dedupe/extraction; we just route once.
    body = "Always validate input. Never trust user data."
    items = classify_review_cues(body=body, source_ref="PR#6")
    assert len(items) == 1
    assert items[0].category == Category.RULES
    assert items[0].snippet == body
    assert set(items[0].signals) == {"cue:always", "cue:never"}


def test_body_with_both_rule_and_bug_cues_produces_two_items() -> None:
    body = "Always validate input. This caused a race condition in prod."
    items = classify_review_cues(body=body, source_ref="PR#7")
    categories = {it.category for it in items}
    assert categories == {Category.RULES, Category.PREVENCOES}
    # both items carry the full body as snippet
    for it in items:
        assert it.snippet == body


def test_snippet_is_full_body_not_a_window() -> None:
    body = "Some preamble. Always validate input. Some trailing context after."
    items = classify_review_cues(body=body, source_ref="PR#8")
    assert len(items) == 1
    assert items[0].snippet == body


def test_long_body_gets_truncated_with_marker() -> None:
    # 0.1.4: long bodies are truncated by truncate_body (~4000 char cap),
    # NOT by the old 240-char sentence window.
    long_body = "always " + ("x" * 5000)
    items = classify_review_cues(body=long_body, source_ref="PR#9")
    assert len(items) == 1
    # snippet was truncated but is still much longer than the old 240-char cap
    assert len(items[0].snippet) > 240
    assert "[... truncated by invocator ...]" in items[0].snippet


def test_trivial_lgtm_body_is_filtered() -> None:
    assert classify_review_cues(body="LGTM", source_ref="PR#10") == []
    assert classify_review_cues(body="lgtm!", source_ref="PR#11") == []
    assert classify_review_cues(body="👍", source_ref="PR#12") == []
    assert classify_review_cues(body="nit", source_ref="PR#13") == []
