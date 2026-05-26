import typer

from invocator import __version__
from invocator.commands.extract import extract_app
from invocator.commands.forge import forge_app
from invocator.commands.scry import scry_app

app = typer.Typer(help="invocator — extract synthesized engineering knowledge from a GitHub repo.")

app.add_typer(forge_app, name="forge")
app.add_typer(scry_app, name="scry")
app.add_typer(extract_app, name="extract")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"invocator {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show invocator version and exit.",
    ),
) -> None:
    return None
