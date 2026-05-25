import re

from invocator.models import Category, ClassifiedItem

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)

_IMPERATIVE_RE = re.compile(
    r"\b(always|never|must|should|don'?t|avoid|prefer|do not)\b",
    re.IGNORECASE | re.MULTILINE,
)

_BUG_PATTERN_RE = re.compile(
    r"\b(regress(?:ion)?|race condition|deadlock|memory leak|leak)\b",
    re.IGNORECASE | re.MULTILINE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_SNIPPET_MAX_CHARS = 240
_REVIEW_CUE_WEIGHT = 3


def _strip_code_fences(text: str) -> str:
    return _FENCED_CODE_RE.sub(" ", text)


def _extract_sentence(*, text: str, match_start: int) -> str:
    segment_start = 0
    for sep_match in _SENTENCE_SPLIT_RE.finditer(text):
        if sep_match.end() <= match_start:
            segment_start = sep_match.end()
        else:
            break
    rest = text[segment_start:]
    parts = _SENTENCE_SPLIT_RE.split(rest, maxsplit=1)
    sentence = parts[0] if parts else rest
    sentence = sentence.strip()
    if len(sentence) > _SNIPPET_MAX_CHARS:
        sentence = sentence[:_SNIPPET_MAX_CHARS].rstrip()
    return sentence


def classify_review_cues(*, body: str | None, source_ref: str) -> list[ClassifiedItem]:
    if not body:
        return []
    cleaned = _strip_code_fences(body)
    items: list[ClassifiedItem] = []
    for match in _IMPERATIVE_RE.finditer(cleaned):
        snippet = _extract_sentence(text=cleaned, match_start=match.start())
        if not snippet:
            continue
        items.append(
            ClassifiedItem(
                category=Category.RULES,
                source_ref=source_ref,
                snippet=snippet,
                weight=_REVIEW_CUE_WEIGHT,
                signals=[f"cue:{match.group(1).lower()}"],
            )
        )
    for match in _BUG_PATTERN_RE.finditer(cleaned):
        snippet = _extract_sentence(text=cleaned, match_start=match.start())
        if not snippet:
            continue
        items.append(
            ClassifiedItem(
                category=Category.PREVENCOES,
                source_ref=source_ref,
                snippet=snippet,
                weight=_REVIEW_CUE_WEIGHT,
                signals=[f"bug:{match.group(1).lower()}"],
            )
        )
    return items
