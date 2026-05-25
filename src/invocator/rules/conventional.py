import re

from invocator.models import Category, ClassifiedItem

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|perf|docs|test|chore|build|ci|revert)(\([^)]+\))?!?:",
    re.IGNORECASE,
)

_TYPE_TO_CATEGORY: dict[str, Category] = {
    "fix": Category.PREVENCOES,
    "revert": Category.PREVENCOES,
    "refactor": Category.PATTERNS,
    "perf": Category.PATTERNS,
}

_CONVENTIONAL_WEIGHT = 2


def parse_conventional(*, title: str) -> tuple[str, str] | None:
    match = _CONVENTIONAL_RE.match(title.strip())
    if not match:
        return None
    type_token = match.group(1).lower()
    scope_token = match.group(2) or ""
    if scope_token.startswith("(") and scope_token.endswith(")"):
        scope_token = scope_token[1:-1]
    return (type_token, scope_token)


def classify_conventional(*, title: str, source_ref: str) -> list[ClassifiedItem]:
    parsed = parse_conventional(title=title)
    if parsed is None:
        return []
    type_token, scope_token = parsed
    category = _TYPE_TO_CATEGORY.get(type_token)
    if category is None:
        return []
    signal = f"conventional:{type_token}"
    if scope_token:
        signal = f"{signal}({scope_token})"
    return [
        ClassifiedItem(
            category=category,
            source_ref=source_ref,
            snippet=title.strip(),
            weight=_CONVENTIONAL_WEIGHT,
            signals=[signal],
        )
    ]
