from pathlib import Path

import pytest

import invocator.config as config_mod
from invocator.config import Settings, load_api_key


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.model == "claude-sonnet-4-6"
    assert settings.top_k_per_category == 500
    assert settings.exclude_bots is True


def test_settings_model_override() -> None:
    settings = Settings(model="claude-opus-4-7")
    assert settings.model == "claude-opus-4-7"


def _patch_config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("invocator.config.CONFIG_FILE", config_file)
    monkeypatch.setattr("invocator.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("invocator.config._env_logged", False)
    # _read_config_file binds CONFIG_FILE as a kw-only default at def-time;
    # repoint that default so load_api_key() reads from the patched path.
    config_mod._read_config_file.__kwdefaults__["path"] = config_file
    return config_file


def _write_key_file(path: Path, key: str) -> None:
    path.write_text(f'[anthropic]\napi_key = "{key}"\n')


def test_load_api_key_returns_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_config_file(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE-ENV")

    result = load_api_key()

    assert result.success is True
    assert result.data == "sk-ant-test-FAKE-ENV"


def test_load_api_key_returns_file_when_no_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = _patch_config_file(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write_key_file(config_file, "sk-ant-test-FAKE-FILE")

    result = load_api_key()

    assert result.success is True
    assert result.data == "sk-ant-test-FAKE-FILE"


def test_load_api_key_neither_returns_no_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_config_file(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = load_api_key()

    assert result.success is False
    assert result.error_code == "NO_API_KEY"


def test_load_api_key_env_overrides_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = _patch_config_file(monkeypatch, tmp_path)
    _write_key_file(config_file, "sk-ant-test-FAKE-FILE")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE-ENV")

    result = load_api_key()

    assert result.success is True
    assert result.data == "sk-ant-test-FAKE-ENV"


def test_load_api_key_env_logs_once_per_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_config_file(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-FAKE-ENV")

    calls: list[tuple] = []

    def fake_info(msg: str, *args: object, **kwargs: object) -> None:
        calls.append((msg, args))

    monkeypatch.setattr(config_mod.logger, "info", fake_info)

    load_api_key()
    load_api_key()
    load_api_key()

    assert len(calls) == 1
