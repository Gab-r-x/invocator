import re

_TRIVIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*$"),
    re.compile(
        r"^(lgtm|nit|nits?|\+1|approved|done|ok|okay|ack|sgtm|wfm|👍|🎉|🚀|✅|✨|💯|👌|🙏|❤️)"
        r"[\.\!\:\s]*$",
        re.IGNORECASE,
    ),
    re.compile(r"^[👍🎉🚀✅✨💯👌🙏❤️🔥\s]+$"),
]

_TRIVIAL_MAX_CHECK_LEN = 40

_BODY_MAX_CHARS = 4000


def is_trivial(body: str | None) -> bool:
    if not body:
        return True
    stripped = body.strip()
    if not stripped:
        return True
    if len(stripped) > _TRIVIAL_MAX_CHECK_LEN:
        return False
    for pat in _TRIVIAL_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def truncate_body(body: str, *, max_chars: int = _BODY_MAX_CHARS) -> str:
    if len(body) <= max_chars:
        return body
    return body[:max_chars].rstrip() + "\n\n[... truncated by invocator ...]"
