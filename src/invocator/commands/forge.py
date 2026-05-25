import os
import tomllib
from pathlib import Path

import anthropic
import tomli_w
import typer
from rich.console import Console

from invocator.config import CONFIG_DIR, CONFIG_FILE
from invocator.result import Result

forge_app = typer.Typer(help="Forge spells — bind pacts (API key management).")

console = Console()
err_console = Console(stderr=True)

VALIDATION_MODEL = "claude-haiku-4-5-20251001"


def _mask_key(*, api_key: str) -> str:
    if len(api_key) <= 11:
        return "***"
    return f"{api_key[:7]}***...{api_key[-4:]}"


def _read_config(*, path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _write_config(*, path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as fh:
        tomli_w.dump(data, fh)
    os.replace(tmp_path, path)
    os.chmod(path, 0o600)


def _validate_api_key(*, api_key: str) -> Result[None]:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model=VALIDATION_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except anthropic.AuthenticationError as exc:
        return Result[None](
            success=False,
            error_code="INVALID_API_KEY",
            error_message=f"Anthropic rejected the API key: {exc}",
        )
    except anthropic.APIStatusError as exc:
        return Result[None](
            success=False,
            error_code="API_STATUS_ERROR",
            error_message=f"Anthropic API error during validation: {exc}",
        )
    return Result[None](success=True)


@forge_app.command("key")
def forge_key(
    show: bool = typer.Option(False, "--show", help="Display the masked stored API key."),
    unset: bool = typer.Option(False, "--unset", help="Remove the stored API key."),
) -> None:
    if show and unset:
        err_console.print("[red]✗[/red] --show and --unset cannot be combined")
        raise typer.Exit(code=2)

    if show:
        data = _read_config(path=CONFIG_FILE)
        key = (data.get("anthropic") or {}).get("api_key")
        if not key:
            console.print("[yellow]No Anthropic API key configured.[/yellow]")
            raise typer.Exit(code=0)
        console.print(f"Stored API key: [cyan]{_mask_key(api_key=key)}[/cyan]")
        raise typer.Exit(code=0)

    if unset:
        if not CONFIG_FILE.exists():
            console.print("[yellow]No config file present; nothing to unset.[/yellow]")
            raise typer.Exit(code=0)
        data = _read_config(path=CONFIG_FILE)
        anthropic_section = data.get("anthropic") or {}
        if "api_key" not in anthropic_section:
            console.print("[yellow]No API key stored; nothing to unset.[/yellow]")
            raise typer.Exit(code=0)
        del anthropic_section["api_key"]
        if anthropic_section:
            data["anthropic"] = anthropic_section
        else:
            data.pop("anthropic", None)
        _write_config(path=CONFIG_FILE, data=data)
        console.print("[green]✓[/green] API key removed.")
        raise typer.Exit(code=0)

    api_key = typer.prompt("Enter your Anthropic API key", hide_input=True)
    api_key = api_key.strip()
    if not api_key:
        err_console.print("[red]✗[/red] Empty API key provided.")
        raise typer.Exit(code=1)

    console.print("Validating API key against Anthropic...")
    validation = _validate_api_key(api_key=api_key)
    if not validation.success:
        masked = _mask_key(api_key=api_key)
        err_console.print(
            f"[red]✗[/red] Validation failed for key [cyan]{masked}[/cyan]: "
            f"{validation.get_error_message()}"
        )
        raise typer.Exit(code=1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = _read_config(path=CONFIG_FILE)
    anthropic_section = data.get("anthropic") or {}
    anthropic_section["api_key"] = api_key
    data["anthropic"] = anthropic_section
    _write_config(path=CONFIG_FILE, data=data)

    masked = _mask_key(api_key=api_key)
    console.print(
        f"[green]✓[/green] Pact bound. Stored API key [cyan]{masked}[/cyan] "
        f"at [dim]{CONFIG_FILE}[/dim]"
    )
