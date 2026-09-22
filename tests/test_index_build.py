import sqlite3
from datetime import date

from purser_core.models import Page, PartName
from purser_ingest.index_build import build_index


def _page(pdf_page, text):
    return Page(
        pdf_page=pdf_page, part=PartName.FOUR, section="4.4", section_title="Evacuations",
        page_in_section=pdf_page, section_total=80, effective=date(2023, 5, 18),
        revision="Issue IX Revision 00", lines=text.split("\n"), text=text,
    )


def test_pages_round_trip_with_lines_intact(tmp_path):
    db = tmp_path / "manual.sqlite"
    build_index([_page(1, "BRACE BRACE\nHEADS DOWN")], db)
    con = sqlite3.connect(db)
    row = con.execute("SELECT lines FROM pages WHERE pdf_page = 1").fetchone()
    import json
    assert json.loads(row[0]) == ["BRACE BRACE", "HEADS DOWN"]


def test_fts_finds_a_page_by_keyword(tmp_path):
    db = tmp_path / "manual.sqlite"
    build_index([_page(1, "Protective Breathing Equipment PBE"), _page(2, "Life raft")], db)
    con = sqlite3.connect(db)
    hits = con.execute(
        "SELECT pdf_page FROM pages_fts WHERE pages_fts MATCH 'PBE'"
    ).fetchall()
    assert [h[0] for h in hits] == [1]


def test_rebuild_is_idempotent(tmp_path):
    db = tmp_path / "manual.sqlite"
    build_index([_page(1, "a")], db)
    build_index([_page(1, "a")], db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM pages").fetchone()[0] == 1
