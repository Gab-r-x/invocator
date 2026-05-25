from invocator.result import Result


def test_result_success_carries_data() -> None:
    result = Result[int](success=True, data=5)
    assert result.data == 5


def test_result_error_message_includes_code_and_message() -> None:
    result = Result[str](success=False, error_message="boom", error_code="X")
    message = result.get_error_message()
    assert "boom" in message
    assert "[X]" in message


def test_add_context_returns_self_and_stores_value() -> None:
    result = Result[int](success=False, error_message="m", error_code="E")
    returned = result.add_context(key="repo", value="owner/name")
    assert returned is result
    assert result.error_context["repo"] == "owner/name"


def test_get_error_message_on_success_returns_empty() -> None:
    result = Result[int](success=True, data=1)
    assert result.get_error_message() == ""
