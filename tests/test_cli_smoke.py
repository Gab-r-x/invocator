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
    # Phase 8 implemented `extract wisdom`; without --repo Typer should
    # exit 2 (missing required option). `--help` should list the flags.
    missing_repo = runner.invoke(app, ["extract", "wisdom"])
    assert missing_repo.exit_code == 2

    help_result = runner.invoke(app, ["extract", "wisdom", "--help"], env={"COLUMNS": "200"})
    assert help_result.exit_code == 0
    combined = help_result.stdout + (help_result.stderr or "")
    assert "wisdom" in combined
    for flag in (
        "--repo",
        "--since",
        "--out",
        "--cache-dir",
        "--model",
        "--top-k",
        "--dry-run",
        "--yes",
        "--force-refetch",
    ):
        assert flag in combined
