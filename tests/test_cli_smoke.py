from typer.testing import CliRunner

from invocator.cli import app

runner = CliRunner()


def test_help_lists_three_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "forge" in result.stdout
    assert "scry" in result.stdout
    assert "extract" in result.stdout


def test_scry_cost_stub() -> None:
    # Phase 4 implemented `scry cost`; without --repo Typer should exit 2
    # (missing required option).
    result = runner.invoke(app, ["scry", "cost"])
    assert result.exit_code == 2


def test_extract_wisdom_stub() -> None:
    # Phase 8 implemented `extract wisdom`. Without --repo, Typer exits 2
    # (missing required option). `--help` returns 0 and mentions the command.
    # We deliberately do NOT enumerate every flag here: Rich's table renderer
    # collapses rows with "..." on narrow terminals, which would make a
    # full-flag-substring assertion brittle across CI runners. The TUI is
    # exercised properly in tests/commands/test_extract.py.
    missing_repo = runner.invoke(app, ["extract", "wisdom"])
    assert missing_repo.exit_code == 2

    help_result = runner.invoke(app, ["extract", "wisdom", "--help"])
    assert help_result.exit_code == 0
    combined = help_result.stdout + (help_result.stderr or "")
    assert "wisdom" in combined
    assert "--repo" in combined
