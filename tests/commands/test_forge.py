import os
import tomllib
from pathlib import Path

import anthropic
import httpx
import pytest
from typer.testing import CliRunner

from invocator.cli import app

runner = CliRunner()

FAKE_KEY = "sk-ant-test-FAKE-abcdefghijklmnop-XYZ4"
EXPECTED_MASK = "sk-ant-***...XYZ4"


class _FakeMessages:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise_exc = raise_exc
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._raise_exc is not None:
            raise self._raise_exc
        return object()


class _FakeAnthropic:
    last_instance: "_FakeAnthropic | None" = None

    def __init__(self, *, api_key: str, raise_exc: Exception | None = None) -> None:
        self.api_key = api_key
        self.messages = _FakeMessages(raise_exc=raise_exc)
        _FakeAnthropic.last_instance = self


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("invocator.commands.forge.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("invocator.commands.forge.CONFIG_FILE", config_file)
    return config_file


def _patch_anthropic_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(*, api_key: str) -> _FakeAnthropic:
        return _FakeAnthropic(api_key=api_key)

    monkeypatch.setattr("invocator.commands.forge.anthropic.Anthropic", factory)


def _patch_anthropic_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(401, request=req)
    exc = anthropic.AuthenticationError("invalid api key", response=resp, body=None)

    def factory(*, api_key: str) -> _FakeAnthropic:
        return _FakeAnthropic(api_key=api_key, raise_exc=exc)

    monkeypatch.setattr("invocator.commands.forge.anthropic.Anthropic", factory)


def test_forge_key_interactive_happy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = _patch_paths(monkeypatch, tmp_path)
    _patch_anthropic_ok(monkeypatch)

    result = runner.invoke(app, ["forge", "key"], input=f"{FAKE_KEY}\n")

    assert result.exit_code == 0, result.output
    assert config_file.exists()
    with config_file.open("rb") as fh:
        data = tomllib.load(fh)
    assert data["anthropic"]["api_key"] == FAKE_KEY


def test_forge_key_interactive_sets_chmod_600(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = _patch_paths(monkeypatch, tmp_path)
    _patch_anthropic_ok(monkeypatch)

    result = runner.invoke(app, ["forge", "key"], input=f"{FAKE_KEY}\n")

    assert result.exit_code == 0, result.output
    mode = os.stat(config_file).st_mode & 0o777
    assert mode == 0o600


def test_forge_key_show_with_stored_key_masks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = _patch_paths(monkeypatch, tmp_path)
    _patch_anthropic_ok(monkeypatch)
    runner.invoke(app, ["forge", "key"], input=f"{FAKE_KEY}\n")
    assert config_file.exists()

    result = runner.invoke(app, ["forge", "key", "--show"])

    assert result.exit_code == 0, result.output
    assert EXPECTED_MASK in result.stdout
    assert FAKE_KEY not in result.stdout


def test_forge_key_show_with_no_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["forge", "key", "--show"])

    assert result.exit_code == 0
    assert "No Anthropic API key configured" in result.stdout


def test_forge_key_unset_removes_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = _patch_paths(monkeypatch, tmp_path)
    _patch_anthropic_ok(monkeypatch)
    runner.invoke(app, ["forge", "key"], input=f"{FAKE_KEY}\n")
    assert config_file.exists()

    unset_result = runner.invoke(app, ["forge", "key", "--unset"])
    assert unset_result.exit_code == 0, unset_result.output

    show_result = runner.invoke(app, ["forge", "key", "--show"])
    assert show_result.exit_code == 0
    assert "No Anthropic API key configured" in show_result.stdout


def test_forge_key_unset_idempotent_no_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["forge", "key", "--unset"])

    assert result.exit_code == 0
    assert "nothing to unset" in result.stdout


def test_forge_key_invalid_key_no_write_no_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = _patch_paths(monkeypatch, tmp_path)
    _patch_anthropic_auth_error(monkeypatch)

    result = runner.invoke(app, ["forge", "key"], input=f"{FAKE_KEY}\n")

    assert result.exit_code != 0
    assert not config_file.exists()
    combined = (result.stdout or "") + (result.stderr or "")
    assert FAKE_KEY not in combined


def test_forge_key_show_and_unset_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["forge", "key", "--show", "--unset"])

    assert result.exit_code == 2


def test_forge_key_empty_input_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["forge", "key"], input="   \n")

    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Empty API key" in combined
