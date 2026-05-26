import re

from invocator.models import Category, ClassifiedItem
from invocator.rules.trivial_filter import is_trivial, truncate_body

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)

_IMPERATIVE_RE = re.compile(
    r"\b(always|never|must|should|don'?t|avoid|prefer|do not)\b",
    re.IGNORECASE | re.MULTILINE,
)

_BUG_PATTERN_RE = re.compile(
    r"\b(regress(?:ion)?|race condition|deadlock|memory leak|leak)\b",
    re.IGNORECASE | re.MULTILINE,
)

_REVIEW_CUE_WEIGHT = 3


def _strip_code_fences(text: str) -> str:
    return _FENCED_CODE_RE.sub(" ", text)


def _collect_unique_cues(*, text: str, pattern: re.Pattern[str]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for match in pattern.finditer(text):
        token = match.group(1).lower()
        if token in seen_set:
            continue
        seen_set.add(token)
        seen.append(token)
    return seen


def classify_review_cues(*, body: str | None, source_ref: str) -> list[ClassifiedItem]:
    # Drop trivial bodies (lgtm/emoji-only/nits) — these never carry signal.
    if is_trivial(body):
        return []
    assert body is not None  # narrowed by is_trivial
    truncated = truncate_body(body)
    # Strip fenced code blocks before matching so "never" inside a code sample
    # doesn't fire a false positive. But the snippet we send to the LLM is the
    # ORIGINAL (truncated) body — the LLM needs surrounding context to judge.
    cleaned = _strip_code_fences(truncated)
    rule_cues = _collect_unique_cues(text=cleaned, pattern=_IMPERATIVE_RE)
    bug_cues = _collect_unique_cues(text=cleaned, pattern=_BUG_PATTERN_RE)
    items: list[ClassifiedItem] = []
    if rule_cues:
        items.append(
            ClassifiedItem(
                category=Category.RULES,
                source_ref=source_ref,
                snippet=truncated,
                weight=_REVIEW_CUE_WEIGHT,
                signals=[f"cue:{c}" for c in rule_cues],
            )
        )
    if bug_cues:
        items.append(
            ClassifiedItem(
                category=Category.PREVENCOES,
                source_ref=source_ref,
                snippet=truncated,
                weight=_REVIEW_CUE_WEIGHT,
                signals=[f"bug:{c}" for c in bug_cues],
            )
        )
    return items
