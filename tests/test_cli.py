import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from purser_ingest.cli import app

PDF = Path(os.environ.get("PURSER_PDF_PATH", ""))
needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="manual PDF not present")


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
