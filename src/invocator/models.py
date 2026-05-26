from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    RULES = "rules"
    PREVENCOES = "prevencoes"
    PATTERNS = "patterns"
    DECISIONS = "decisions"
    GLOSSARY = "glossary"


class RepoRef(BaseModel):
    owner: str
    name: str


class PullRequest(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = Field(default_factory=list)
    author_login: str
    merged_at_utc: datetime | None = None
    created_at_utc: datetime
    updated_at_utc: datetime


class Issue(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = Field(default_factory=list)
    author_login: str
    created_at_utc: datetime
    updated_at_utc: datetime


class Commit(BaseModel):
    sha: str
    message: str
    author_login: str | None = None
    authored_at_utc: datetime


class ReviewComment(BaseModel):
    id: int
    pr_number: int
    author_login: str
    body: str
    created_at_utc: datetime


class IssueComment(BaseModel):
    id: int
    issue_or_pr_number: int
    author_login: str
    body: str
    created_at_utc: datetime


class ClassifiedItem(BaseModel):
    category: Category
    source_ref: str
    snippet: str
    weight: int
    signals: list[str] = Field(default_factory=list)


# Anthropic input pricing per 1M input tokens, in USD cents (e.g. $3.00 -> 300).
MODEL_PRICING_INPUT_USD_CENTS_PER_MILLION: dict[str, int] = {
    "claude-sonnet-4-6": 300,
    "claude-opus-4-7": 1500,
    "claude-haiku-4-5": 100,
}

# Anthropic output pricing per 1M output tokens, in USD cents (e.g. $15.00 -> 1500).
MODEL_PRICING_OUTPUT_USD_CENTS_PER_MILLION: dict[str, int] = {
    "claude-sonnet-4-6": 1500,
    "claude-opus-4-7": 7500,
    "claude-haiku-4-5": 500,
}


class CostEstimate(BaseModel):
    estimated_tokens: int
    estimated_cost_usd_cents: int
    estimated_minutes: int
    per_resource: dict[str, int] = Field(default_factory=dict)


class SummonStats(BaseModel):
    pulls_count: int
    issues_count: int
    commits_count: int
    pr_review_comments_count: int
    issue_comments_count: int
    started_at_utc: datetime
    finished_at_utc: datetime


class ClassifyStats(BaseModel):
    rules_count: int = 0
    prevencoes_count: int = 0
    patterns_count: int = 0
    decisions_count: int = 0
    glossary_count: int = 0
    total_items_processed: int = 0
    total_classified: int = 0
    dropped_dupes: int = 0
    dropped_top_k: int = 0


class SynthesisOutput(BaseModel):
    category: Category
    markdown: str
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_cents: int = 0


class SynthesisStats(BaseModel):
    rules_cost_usd_cents: int = 0
    prevencoes_cost_usd_cents: int = 0
    patterns_cost_usd_cents: int = 0
    decisions_cost_usd_cents: int = 0
    glossary_cost_usd_cents: int = 0
    total_cost_usd_cents: int = 0
    categories_cached: int = 0
    categories_synthesized: int = 0
    categories_dry_run_dumped: int = 0
    categories_skipped_empty: int = 0
    started_at_utc: datetime
    finished_at_utc: datetime
