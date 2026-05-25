from datetime import datetime, timezone

from invocator.models import (
    Category,
    ClassifiedItem,
    ClassifyStats,
    Issue,
    PullRequest,
    RepoRef,
    SummonStats,
)


def test_category_enum_values() -> None:
    assert Category.RULES.value == "rules"
    assert Category.PREVENCOES.value == "prevencoes"
    assert Category.PATTERNS.value == "patterns"
    assert Category.DECISIONS.value == "decisions"
    assert Category.GLOSSARY.value == "glossary"
    assert len(list(Category)) == 5


def test_repo_ref_round_trip() -> None:
    ref = RepoRef(owner="x", name="y")
    assert ref.model_dump() == {"owner": "x", "name": "y"}


def test_classified_item_signals_default_empty() -> None:
    item = ClassifiedItem(
        category=Category.RULES,
        source_ref="PR#1",
        snippet="always validate input",
        weight=3,
    )
    assert item.signals == []


def test_summon_stats_round_trip_zero_counts() -> None:
    ts = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    stats = SummonStats(
        pulls_count=0,
        issues_count=0,
        commits_count=0,
        pr_review_comments_count=0,
        issue_comments_count=0,
        started_at_utc=ts,
        finished_at_utc=ts,
    )
    dumped = stats.model_dump()
    assert dumped["pulls_count"] == 0
    assert SummonStats(**dumped) == stats


def test_pull_request_accepts_id() -> None:
    pr = PullRequest(
        id=42,
        number=1,
        title="t",
        state="open",
        author_login="alice",
        created_at_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at_utc=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    assert pr.id == 42


def test_classify_stats_round_trip_zero_fields() -> None:
    stats = ClassifyStats()
    dumped = stats.model_dump()
    assert dumped["rules_count"] == 0
    assert dumped["prevencoes_count"] == 0
    assert dumped["patterns_count"] == 0
    assert dumped["decisions_count"] == 0
    assert dumped["glossary_count"] == 0
    assert dumped["total_items_processed"] == 0
    assert dumped["total_classified"] == 0
    assert dumped["dropped_dupes"] == 0
    assert dumped["dropped_top_k"] == 0
    assert ClassifyStats(**dumped) == stats


def test_issue_accepts_id() -> None:
    issue = Issue(
        id=99,
        number=2,
        title="t",
        state="open",
        author_login="bob",
        created_at_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at_utc=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    assert issue.id == 99
