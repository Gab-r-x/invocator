from invocator.rules.trivial_filter import is_trivial, truncate_body


def test_is_trivial_empty() -> None:
    assert is_trivial(None) is True
    assert is_trivial("") is True
    assert is_trivial("   \n\t  ") is True


def test_is_trivial_lgtm_variants() -> None:
    assert is_trivial("LGTM") is True
    assert is_trivial("lgtm") is True
    assert is_trivial("LGTM!") is True
    assert is_trivial("lgtm.") is True
    assert is_trivial("LGTM ") is True


def test_is_trivial_nit_and_thumbs() -> None:
    assert is_trivial("nit") is True
    assert is_trivial("nit:") is True
    assert is_trivial("+1") is True
    assert is_trivial("ok") is True
    assert is_trivial("done") is True


def test_is_trivial_emoji_only() -> None:
    assert is_trivial("👍") is True
    assert is_trivial("🎉") is True
    assert is_trivial("👍👍") is True
    assert is_trivial("✅ 🚀") is True


def test_is_trivial_keeps_real_comments() -> None:
    assert is_trivial("LGTM, but rename foo to bar.") is False
    assert is_trivial("This logic is wrong because of X.") is False
    assert is_trivial("Always validate input.") is False


def test_is_trivial_long_string_is_not_trivial() -> None:
    # A body over the check length is never trivial, even if it starts with lgtm.
    assert is_trivial("lgtm but actually here are 60 chars of real content blah blah") is False


def test_truncate_body_under_limit_returns_unchanged() -> None:
    body = "short body"
    assert truncate_body(body) == body


def test_truncate_body_over_limit_truncates_and_marks() -> None:
    body = "x" * 5000
    truncated = truncate_body(body)
    assert len(truncated) < len(body) + 50
    assert "[... truncated by invocator ...]" in truncated


def test_truncate_body_custom_max() -> None:
    body = "x" * 100
    truncated = truncate_body(body, max_chars=50)
    assert "[... truncated by invocator ...]" in truncated
    assert truncated.startswith("x" * 50)
