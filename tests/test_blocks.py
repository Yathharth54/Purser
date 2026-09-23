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
