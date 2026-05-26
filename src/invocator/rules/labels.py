from invocator.models import Category, ClassifiedItem
from invocator.rules.trivial_filter import truncate_body

DEFAULT_LABEL_MAP: dict[str, Category] = {
    "bug": Category.PREVENCOES,
    "regression": Category.PREVENCOES,
    "architecture": Category.DECISIONS,
    "adr": Category.DECISIONS,
    "decision": Category.DECISIONS,
    "rfc": Category.DECISIONS,
    "refactor": Category.PATTERNS,
    "tech-debt": Category.PATTERNS,
    "pattern": Category.PATTERNS,
    "convention": Category.RULES,
    "style": Category.RULES,
    "lint": Category.RULES,
    "domain": Category.GLOSSARY,
    "glossary": Category.GLOSSARY,
}

_LABEL_WEIGHT = 1


def classify_labels(
    *,
    labels: list[str],
    source_ref: str,
    title: str,
    body: str | None = None,
) -> list[ClassifiedItem]:
    items: list[ClassifiedItem] = []
    title_clean = title.strip() if title and title.strip() else "<no title>"
    if body and body.strip():
        snippet = f"{title_clean}\n\n{truncate_body(body)}"
    else:
        snippet = title_clean
    for raw_label in labels:
        if not raw_label:
            continue
        normalized = raw_label.strip().lower()
        category = DEFAULT_LABEL_MAP.get(normalized)
        if category is None:
            continue
        items.append(
            ClassifiedItem(
                category=category,
                source_ref=source_ref,
                snippet=snippet,
                weight=_LABEL_WEIGHT,
                signals=[f"label:{normalized}"],
            )
        )
    return items
