import logging
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from invocator.result import Result

CONFIG_DIR = Path.home() / ".invocator"
CONFIG_FILE = CONFIG_DIR / "config.toml"
ENV_API_KEY = "ANTHROPIC_API_KEY"
ENV_CACHE_DIR = "INVOCATOR_CACHE_DIR"

logger = logging.getLogger(__name__)

_env_logged = False


class Settings(BaseModel):
    cache_dir: Path = Field(default_factory=lambda: Path("./.cache/invocator"))
    out_dir: Path = Field(default_factory=lambda: Path("./learnings"))
    model: str = "claude-sonnet-4-6"
    top_k_per_category: int = 500
    exclude_bots: bool = True


def _read_config_file(*, path: Path = CONFIG_FILE) -> Result[dict]:
    if not path.exists():
        return Result[dict](success=True, data={})
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        return Result[dict](
            success=False,
            error_code="CONFIG_READ_FAILED",
            error_message=f"Failed to read config file: {exc}",
        ).add_context(key="path", value=str(path))
    except tomllib.TOMLDecodeError as exc:
        return Result[dict](
            success=False,
            error_code="CONFIG_PARSE_FAILED",
            error_message=f"Failed to parse config TOML: {exc}",
        ).add_context(key="path", value=str(path))
    return Result[dict](success=True, data=data)


def load_api_key() -> Result[str]:
    global _env_logged
    env_value = os.environ.get(ENV_API_KEY)
    if env_value:
        if not _env_logged:
            logger.info("Using Anthropic API key from %s env var", ENV_API_KEY)
            _env_logged = True
        return Result[str](success=True, data=env_value)

    read = _read_config_file()
    if not read.success:
        return Result[str](
            success=False,
            error_code=read.error_code,
            error_message=read.error_message,
            error_context=read.error_context,
        )

    data = read.data or {}
    anthropic_section = data.get("anthropic") or {}
    key = anthropic_section.get("api_key")
    if not key or not isinstance(key, str):
        return Result[str](
            success=False,
            error_code="NO_API_KEY",
            error_message="No Anthropic API key configured. Run: invocator forge key",
        )
    return Result[str](success=True, data=key)


def resolve_cache_dir(*, settings: Settings) -> Path:
    env_value = os.environ.get(ENV_CACHE_DIR)
    if env_value:
        return Path(env_value).expanduser()
    return settings.cache_dir
