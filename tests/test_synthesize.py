import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import pytest

from invocator import synthesize as synth_mod
from invocator.config import Settings
from invocator.models import (
    Category,
    ClassifiedItem,
    RepoRef,
    SynthesisOutput,
    SynthesisStats,
)
from invocator.result import Result
from invocator.synthesize import (
    build_corpus,
    count_tokens_estimate,
    log_usage,
    synthesize_all,
    synthesize_category,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeUsage:
    def __init__(
        self,
        *,
        input_tokens: int = 1000,
        cache_creation_input_tokens: int | None = 500,
        cache_read_input_tokens: int | None = 0,
        output_tokens: int = 200,
    ) -> None:
        self.input_tokens = input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, text: str = "# Rules\n\n- foo", **usage_kwargs: Any) -> None:
        self.content = [FakeContent(text)]
        self.usage = FakeUsage(**usage_kwargs)


class FakeMessages:
    def __init__(self, response: Any | None = None) -> None:
        self.response = response if response is not None else FakeResponse()
        self.calls: list[dict] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response

    # For count_tokens fake usage
    def count_tokens(self, **kwargs: Any) -> Any:
        class _R:
            input_tokens = 12345

        return _R()


class FakeClient:
    def __init__(self, response: Any | None = None) -> None:
        self.messages = FakeMessages(response)


class RaisingMessages:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        raise self.exc


class RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.messages = RaisingMessages(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(tmp_path: Path) -> Settings:
    return Settings(out_dir=tmp_path / "learnings", cache_dir=tmp_path / "cache")


def _repo() -> RepoRef:
    return RepoRef(owner="o", name="n")


def _write_classified(
    *, settings: Settings, repo: RepoRef, category: Category, items: list[dict]
) -> None:
    repo_dir = settings.cache_dir / f"{repo.owner}__{repo.name}"
    classified = repo_dir / "classified"
    classified.mkdir(parents=True, exist_ok=True)
    with (classified / f"{category.value}.jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item) + "\n")


def _seed_all_categories(*, settings: Settings, repo: RepoRef) -> None:
    for cat in Category:
        _write_classified(
            settings=settings,
            repo=repo,
            category=cat,
            items=[
                {
                    "category": cat.value,
                    "source_ref": f"PR#{cat.value}-1",
                    "snippet": f"snippet for {cat.value}",
                    "weight": 1,
                    "signals": ["sig"],
                }
            ],
        )


# ---------------------------------------------------------------------------
# build_corpus
# ---------------------------------------------------------------------------


def test_build_corpus_empty_list_returns_empty_string() -> None:
    assert build_corpus(classified_items=[]) == ""


def test_build_corpus_three_items_contains_refs_and_escapes_quotes() -> None:
    items = [
        ClassifiedItem(
            category=Category.RULES,
            source_ref="PR#1",
            snippet='use "quotes" here',
            weight=1,
            signals=["a"],
        ),
        ClassifiedItem(
            category=Category.RULES, source_ref="PR#2", snippet="plain", weight=1, signals=[]
        ),
        ClassifiedItem(
            category=Category.RULES,
            source_ref="commit:abc1234",
            snippet="third item",
            weight=1,
            signals=["b", "c"],
        ),
    ]
    out = build_corpus(classified_items=items)
    assert "PR#1" in out
    assert "PR#2" in out
    assert "commit:abc1234" in out
    assert "plain" in out
    assert "third item" in out
    # quotes escaped: original `"quotes"` becomes `\"quotes\"`
    assert '\\"quotes\\"' in out


# ---------------------------------------------------------------------------
# count_tokens_estimate
# ---------------------------------------------------------------------------


def test_count_tokens_estimate_no_env_uses_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys_text = "x" * 100
    corpus = "y" * 300
    assert count_tokens_estimate(system=sys_text, corpus=corpus) == (100 + 300) // 4


def test_count_tokens_estimate_attribute_error_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE")

    class BadMessages:
        def count_tokens(self, **kwargs: Any) -> Any:
            raise AttributeError("no count_tokens")

    class BadClient:
        messages = BadMessages()

    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: BadClient())
    sys_text = "abcd" * 25  # len 100
    corpus = "efgh" * 25  # len 100
    assert count_tokens_estimate(system=sys_text, corpus=corpus) == (100 + 100) // 4


def test_count_tokens_estimate_uses_sdk_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE")
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: FakeClient())
    assert count_tokens_estimate(system="sys", corpus="corp") == 12345


# ---------------------------------------------------------------------------
# log_usage
# ---------------------------------------------------------------------------


def test_log_usage_all_fields_non_negative_cost() -> None:
    response = FakeResponse(
        input_tokens=1000,
        cache_creation_input_tokens=500,
        cache_read_input_tokens=2000,
        output_tokens=200,
    )
    cost = log_usage(response=response, category=Category.RULES, model="claude-sonnet-4-6")
    assert cost >= 0


def test_log_usage_missing_cache_fields_defaults_to_zero() -> None:
    response = FakeResponse(
        input_tokens=1000,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        output_tokens=200,
    )
    # Must not raise
    cost = log_usage(response=response, category=Category.PATTERNS, model="claude-sonnet-4-6")
    assert cost >= 0


# ---------------------------------------------------------------------------
# synthesize_category
# ---------------------------------------------------------------------------


def test_synthesize_category_happy() -> None:
    client = FakeClient(response=FakeResponse(text="# Rules\n\n- bar"))
    result = synthesize_category(
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        category=Category.RULES,
        corpus="some corpus",
        instruction="write rules",
    )
    assert result.success is True
    assert result.data is not None
    assert result.data.category is Category.RULES
    assert "# Rules" in result.data.markdown
    assert result.data.input_tokens == 1000
    assert result.data.output_tokens == 200


def test_synthesize_category_request_payload_shape() -> None:
    client = FakeClient()
    synthesize_category(
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        category=Category.RULES,
        corpus="my-corpus",
        instruction="my-instruction",
    )
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    # system is a list with one block carrying ephemeral cache_control
    assert isinstance(call["system"], list)
    assert len(call["system"]) == 1
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    # user content: corpus (cache_control) + instruction (no cache_control)
    user_content = call["messages"][0]["content"]
    assert len(user_content) == 2
    assert user_content[0]["text"] == "my-corpus"
    assert user_content[0]["cache_control"] == {"type": "ephemeral"}
    assert user_content[1]["text"] == "my-instruction"
    assert "cache_control" not in user_content[1]
    assert call["temperature"] == 0
    assert call["max_tokens"] == 8000


def test_synthesize_category_api_error_returns_result_failure() -> None:
    # anthropic.APIError needs a request arg in newer SDKs; build minimal one.
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIError("boom", request=request, body=None)
    client = RaisingClient(exc)
    result = synthesize_category(
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        category=Category.RULES,
        corpus="x",
        instruction="y",
    )
    assert result.success is False
    assert result.error_code == "ANTHROPIC_API_ERROR"
    assert result.error_context.get("category") == "rules"


# ---------------------------------------------------------------------------
# synthesize_all
# ---------------------------------------------------------------------------


def test_synthesize_all_dry_run_writes_files_without_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    def _boom(*, api_key: str) -> Any:
        raise AssertionError("client must not be constructed in dry-run")

    monkeypatch.setattr(synth_mod, "_get_client", _boom)

    result = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=True)

    assert result.success is True
    out_dir = settings.out_dir
    for cat in Category:
        path = out_dir / f"{cat.value}.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "dry-run dump" in content
        assert f"PR#{cat.value}-1" in content
    assert (out_dir / "INDEX.md").exists()


def test_synthesize_all_real_run_writes_md_and_hash_and_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )

    client = FakeClient(response=FakeResponse(text="# Cat\n\n- entry"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client)
    # avoid SDK call inside count_tokens_estimate
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 100)

    result = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)

    assert result.success is True
    assert result.data is not None
    out_dir = settings.out_dir
    for cat in Category:
        assert (out_dir / f"{cat.value}.md").exists()
        assert (out_dir / ".cache" / f"{cat.value}.hash").exists()
    index = (out_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "o/n" in index
    assert "claude-sonnet-4-6" in index
    assert "Total cost" in index
    assert "Cached categories" in index
    assert len(client.messages.calls) == 5


def test_synthesize_all_hash_cache_hit_skips_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 100)

    client1 = FakeClient(response=FakeResponse(text="# Cat\n\n- entry"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client1)
    first = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert first.success is True

    # Capture md content
    rules_md_before = (settings.out_dir / "rules.md").read_text(encoding="utf-8")

    # Second run with a brand-new client — none of the categories should call create
    client2 = FakeClient(response=FakeResponse(text="# Different\n\n- changed"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client2)
    second = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert second.success is True
    assert second.data is not None
    assert second.data.categories_cached == 5
    assert len(client2.messages.calls) == 0

    rules_md_after = (settings.out_dir / "rules.md").read_text(encoding="utf-8")
    assert rules_md_after == rules_md_before


def test_synthesize_all_hash_cache_miss_re_synthesizes_only_changed_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 100)

    client1 = FakeClient(response=FakeResponse(text="# Cat\n\n- entry"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client1)
    synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert len(client1.messages.calls) == 5

    # Modify only the RULES classified bucket
    _write_classified(
        settings=settings,
        repo=repo,
        category=Category.RULES,
        items=[
            {
                "category": "rules",
                "source_ref": "PR#rules-new",
                "snippet": "newly added",
                "weight": 2,
                "signals": [],
            }
        ],
    )

    client2 = FakeClient(response=FakeResponse(text="# Cat\n\n- updated"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client2)
    second = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert second.success is True
    assert second.data is not None
    assert len(client2.messages.calls) == 1
    assert second.data.categories_cached == 4
    assert second.data.categories_synthesized == 1


def test_synthesize_all_no_api_key_propagates_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=False, error_code="NO_API_KEY", error_message="missing"),
    )

    result = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert result.success is False
    assert result.error_code == "NO_API_KEY"


def test_synthesize_all_index_contains_counts_and_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 100)
    client = FakeClient(response=FakeResponse(text="# Title\n\n- one\n- two"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client)

    result = synthesize_all(settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False)
    assert result.success is True
    index = (settings.out_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "# Learnings — o/n" in index
    assert "claude-sonnet-4-6" in index
    assert "Total cost: $" in index
    assert "Cached categories: 0/5" in index
    assert "rules.md" in index
    assert "prevencoes.md" in index
    assert "patterns.md" in index
    assert "decisions.md" in index
    assert "glossary.md" in index


def test_synthesize_all_token_cap_skips_category_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )
    # Over the 200k soft cap → skip every category
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 300_000)
    client = FakeClient()
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client)

    result = synthesize_all(
        settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False, force=False
    )
    assert result.success is True
    assert len(client.messages.calls) == 0
    # No category .md should have been written from a synthesis
    for cat in Category:
        assert not (settings.out_dir / f"{cat.value}.md").exists()
        assert not (settings.out_dir / ".cache" / f"{cat.value}.hash").exists()
    # INDEX still rendered
    assert (settings.out_dir / "INDEX.md").exists()


def test_synthesize_all_token_cap_force_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    repo = _repo()
    _seed_all_categories(settings=settings, repo=repo)

    monkeypatch.setattr(
        "invocator.config.load_api_key",
        lambda: Result[str](success=True, data="sk-ant-test-FAKE"),
    )
    monkeypatch.setattr(synth_mod, "count_tokens_estimate", lambda *, system, corpus: 300_000)
    client = FakeClient(response=FakeResponse(text="# Forced\n\n- ok"))
    monkeypatch.setattr(synth_mod, "_get_client", lambda *, api_key: client)

    result = synthesize_all(
        settings=settings, repo=repo, model="claude-sonnet-4-6", dry_run=False, force=True
    )
    assert result.success is True
    assert len(client.messages.calls) == 5


# ---------------------------------------------------------------------------
# Model round-trip
# ---------------------------------------------------------------------------


def test_synthesis_output_round_trip() -> None:
    out = SynthesisOutput(
        category=Category.RULES,
        markdown="# x",
        input_tokens=1,
        cache_creation_input_tokens=2,
        cache_read_input_tokens=3,
        output_tokens=4,
        cost_usd_cents=5,
    )
    rebuilt = SynthesisOutput.model_validate(out.model_dump())
    assert rebuilt == out


def test_synthesis_stats_round_trip() -> None:
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    stats = SynthesisStats(started_at_utc=now, finished_at_utc=now)
    rebuilt = SynthesisStats.model_validate(stats.model_dump())
    assert rebuilt == stats
