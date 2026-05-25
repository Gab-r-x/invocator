import typer

from invocator.commands.extract import extract_app
from invocator.commands.forge import forge_app
from invocator.commands.scry import scry_app

app = typer.Typer(help="invocator — extract synthesized engineering knowledge from a GitHub repo.")

app.add_typer(forge_app, name="forge")
app.add_typer(scry_app, name="scry")
app.add_typer(extract_app, name="extract")
