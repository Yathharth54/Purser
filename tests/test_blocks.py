"""The manual's text layer is structured; a line dump throws that away.

Measured on pdf_page 552:
    ind=0   2. CREW RESPONSIBILTIES              -> heading
    ind=5   <bullet> Inform the PIC immediately of the source, colour, density of the
    ind=9   smoke (if present), and its effects  -> WRAPPED CONTINUATION of the bullet
    ind=4   Note: Kindly refer to PART THREE     -> note
    ind=34  Table 4.2B                           -> caption
    ind=10  MID AIR SMOKE FILLED CABIN  CABIN CREW ACTIONS  -> genuine two columns

Rendering that line by line is why the manual reads as though it were scanned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from purser_core.blocks import BULLET_GLYPHS, parse_blocks
from purser_core.corpus import Corpus

BULLET = ""  # the Wingdings bullet the manual actually uses, 4,326 times

needs_index = pytest.mark.skipif(
    not Path("data/manual.sqlite").is_file(), reason="needs the built index"
)


def test_numbered_heading_at_the_margin():
    out = parse_blocks(["2. CREW RESPONSIBILTIES"], [])
    assert [(b.kind, b.text) for b in out] == [("heading", "2. CREW RESPONSIBILTIES")]


def test_a_wrapped_bullet_is_rejoined_into_one_sentence():
    lines = [
        "     " + BULLET + "   Inform the PIC immediately of the source, colour, density of the",
        "         smoke (if present), and its effects on passengers.",
    ]
    [b] = parse_blocks(lines, [])
    assert b.kind == "bullet"
    assert b.text == (
        "Inform the PIC immediately of the source, colour, density of the "
        "smoke (if present), and its effects on passengers."
    )


def test_a_short_line_is_NOT_swallowed_as_a_continuation():
    """The width test is what makes rejoining safe.

    'Note: Kindly refer to PART THREE for details' is short -- it did not run to
    the column limit -- so the heading beneath it is a new block, not its tail.
    Without this rule the parser eats the next line every time.
    """
    lines = [
        "    Note: Kindly refer to PART THREE for details",
        "     Mid-air smoke filled cabin commands and course of action",
        "    ..........................................................................."
        ".............",
    ]
    out = parse_blocks(lines, [])
    assert out[0].kind == "note"
    assert "Mid-air" not in out[0].text


def test_a_table_keeps_its_columns_verbatim():
    lines = [
        "                     Table 4.2B",
        "      MID AIR SMOKE FILLED CABIN               CABIN CREW ACTIONS",
        "             STAY LOW                  For smoke during approach",
    ]
    out = parse_blocks(lines, [])
    assert [b.kind for b in out] == ["caption", "table"]
    # the column gaps survive -- they are the only thing pairing the two columns
    assert "STAY LOW                  For smoke" in out[1].text


def test_chrome_indices_are_excluded():
    lines = ["InterGlobe Aviation Limited   ifly.SEP", "1. GENERAL"]
    out = parse_blocks(lines, [0])
    assert [b.kind for b in out] == ["heading"]


@needs_index
def test_page_552_parses_into_the_expected_shape():
    page = Corpus("data").page(552)
    out = parse_blocks(page.lines, page.chrome)
    kinds = [b.kind for b in out]
    assert kinds[0] == "heading"
    assert out[0].text.startswith("2. CREW RESPONSIBILTIES")
    assert kinds.count("bullet") >= 4
    assert "table" in kinds
    # every bullet is a whole sentence, not a fragment ending mid-clause
    for b in out:
        if b.kind == "bullet":
            assert not b.text.endswith(" of the")


@needs_index
def test_a_table_does_not_swallow_the_rest_of_the_page():
    """A runaway table must not absorb everything below it for the rest of the page.

    On pdf_page 594, 'Table 4.4D' is exactly two rows (SIGNAL FOR BRACE / COMMANDS).
    Everything from 'Planned Emergency (Ditching)' onward -- prose plus a nine-step
    bulleted procedure -- is NOT part of that table. A parser that only closes a
    table on a fresh caption or a margin-numbered heading never sees a reason to
    stop, and swallows the whole rest of the page into one monospace table block:
    exactly the "reads like a scan" failure this parser exists to eliminate,
    reproduced *inside* a table.
    """
    page = Corpus("data").page(594)
    out = parse_blocks(page.lines, page.chrome)
    tables = [b for b in out if b.kind == "table"]
    assert len(tables) == 1
    assert "Step 1" not in tables[0].text
    assert "Ditching" not in tables[0].text
    steps = [b.text for b in out if b.kind == "bullet" and b.text.startswith("Step ")]
    assert len(steps) == 9


@needs_index
def test_a_caption_with_an_aircraft_suffix_still_opens_its_table():
    """'Table 4.4Y (A-320)' must open a table, not fall through to prose.

    On pdf_page 631, the caption is followed by the emergency-assignment grid
    (Position | Duties and assignments) -- who does what during an
    evacuation, and A-320 vs A-321 changes door and equipment layout. A
    caption regex that only accepts a single trailing letter ('Table 4.4B')
    misses the '(A-320)' suffix entirely, so the caption is never recognised,
    no table opens, and the whole two-column grid renders as run-together
    bullets/para -- exactly the failure this parser exists to eliminate, on
    the highest-stakes content in the manual.
    """
    page = Corpus("data").page(631)
    out = parse_blocks(page.lines, page.chrome)
    captions = [b.text for b in out if b.kind == "caption"]
    assert "Table 4.4Y (A-320)" in captions
    tables = [b for b in out if b.kind == "table"]
    assert len(tables) == 1
    assert "Position" in tables[0].text
    assert "Duties and assignments" in tables[0].text
    assert "Captain" in tables[0].text


@needs_index
def test_no_content_is_lost_anywhere_in_the_corpus():
    """Every non-blank, non-chrome line must survive into some block.

    A parser that silently drops a line it does not recognise is the failure
    mode that matters here: she would never know a step was missing.
    """
    corpus = Corpus("data")
    for pdf_page in (551, 552, 594, 600, 1, 1226):
        page = corpus.page(pdf_page)
        joined = " ".join(b.text for b in parse_blocks(page.lines, page.chrome))
        squashed = " ".join(joined.split())
        for i, line in page.content_lines():
            # The bullet glyph is decorative -- the parser deliberately strips it
            # from bullet text (see test_a_wrapped_bullet_is_rejoined_into_one_sentence),
            # so it must not be part of the "content" this probe checks for.
            words = [w for w in line.split() if w.strip(BULLET_GLYPHS)]
            if len(words) >= 3:
                probe = " ".join(words[:3])
                assert probe in squashed, f"page {pdf_page} line {i} vanished: {line!r}"
