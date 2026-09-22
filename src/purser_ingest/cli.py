from __future__ import annotations

import json
from pathlib import Path

import typer

from purser_ingest.assemble import assemble
from purser_ingest.embed_build import build_vectors
from purser_ingest.extract import extract_pages
from purser_ingest.glossary_miner import mine_glossary
from purser_ingest.index_build import build_index
from purser_ingest.toc_build import build_toc

app = typer.Typer(help="Purser ingest — PDF to searchable index.")

_PDF_ARGUMENT = typer.Argument(..., exists=True, readable=True)
_OUT_OPTION = typer.Option(Path("data"), "--out", help="Output directory")


@app.callback()
def _main() -> None:
    """Purser ingest — PDF to searchable index."""


@app.command()
def ingest(
    pdf: Path = _PDF_ARGUMENT,
    out: Path = _OUT_OPTION,
) -> None:
    """Parse the manual into data/. Run once per manual revision."""
    out.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Extracting text from {pdf.name} ...")
    raw = extract_pages(pdf)
    typer.echo(f"  {len(raw)} pages")

    typer.echo("Parsing tree coordinates from page footers ...")
    pages = assemble(raw)

    typer.echo("Building Part/Section tree ...")
    toc = build_toc(pages)
    (out / "toc.json").write_text(json.dumps([n.model_dump(mode="json") for n in toc], indent=2))
    typer.echo(f"  {len([n for n in toc if n.section])} numbered sections")

    typer.echo("Mining glossary ...")
    glossary = mine_glossary(pages)
    (out / "glossary.json").write_text(
        json.dumps([g.model_dump(mode="json") for g in glossary], indent=2)
    )
    typer.echo(f"  {len(glossary)} terms")

    typer.echo("Building SQLite index with FTS5 ...")
    build_index(pages, out / "manual.sqlite")

    typer.echo(f"Embedding {len(pages)} pages (first run downloads the model, can be slow) ...")
    build_vectors(pages, out / "vectors.npy")

    typer.echo(f"Done. Index written to {out}/")
