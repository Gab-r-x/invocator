import re

from invocator.models import Category, ClassifiedItem
from invocator.rules.trivial_filter import truncate_body

_SECTION_HEADERS = ("context", "decision", "consequences", "alternatives")

_SECTION_RE = re.compile(
    r"(?im)^\s*##\s+(context|decision|consequences|alternatives)\b",
)

_ADR_TITLE_RE = re.compile(r"^\s*adr-", re.IGNORECASE)

_ADR_WEIGHT = 5


def _matched_sections(*, body: str) -> set[str]:
    found: set[str] = set()
    for match in _SECTION_RE.finditer(body):
        found.add(match.group(1).lower())
    return found & set(_SECTION_HEADERS)


def classify_adr(
    *,
    title: str,
    body: str | None,
    source_ref: str,
) -> list[ClassifiedItem]:
    title_match = bool(_ADR_TITLE_RE.match(title or ""))
    section_count = 0
    if body:
        section_count = len(_matched_sections(body=body))
    if not title_match and section_count < 2:
        return []
    title_clean = (title or "").strip() or "<no title>"
    if body and body.strip():
        snippet = f"{title_clean}\n\n{truncate_body(body)}"
    else:
        snippet = title_clean
    return [
        ClassifiedItem(
            category=Category.DECISIONS,
            source_ref=source_ref,
            snippet=snippet,
            weight=_ADR_WEIGHT,
            signals=["adr"],
        )
    ]
