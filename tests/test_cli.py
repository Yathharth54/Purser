import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from purser_ingest.cli import app

PDF = Path(os.environ.get("PURSER_PDF_PATH", ""))
needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="manual PDF not present")


def test_help_lists_ingest_subcommand():
    """Ungated regression for the Typer-subcommand wiring: CI without the manual
    PDF previously had zero coverage of this, since the only other CLI test is
    @needs_pdf-gated. Without @app.callback(), a single-command Typer app
    collapses and treats the literal word "ingest" as the PDF path -- but the
    app's own help string ("Purser ingest -- PDF to searchable index.") also
    contains "ingest" in both the group and collapsed forms, so a plain
    substring check on that word can't detect the collapse. "Commands" only
    appears in the group (multi-command) help output.
    """
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Commands" in result.output


@needs_pdf
def test_ingest_writes_all_four_artifacts(tmp_path):
    result = CliRunner().invoke(app, ["ingest", str(PDF), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output

    for name in ("manual.sqlite", "vectors.npy", "toc.json", "glossary.json"):
        assert (tmp_path / name).is_file(), f"{name} not written"

    toc = json.loads((tmp_path / "toc.json").read_text())
    sections = {n["section"] for n in toc if n["section"]}
    assert "4.4" in sections and "6.7" in sections
    assert len(sections) == 37

    glossary = json.loads((tmp_path / "glossary.json").read_text())
    terms = {g["term"] for g in glossary}
    assert {"ABP", "PAX", "PBE"} <= terms
