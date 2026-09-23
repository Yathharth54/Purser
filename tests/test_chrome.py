"""Page furniture is identified, never removed.

The manual prints the same six boilerplate lines on almost every page -- 6,100
lines, with 19,347 more blank, together 51% of the manual's 49,723 lines. They
are noise to every reader we have: they waste the agent's context, dilute page
vectors, and render as a wall of letterhead in the manual browser.

This module reports WHICH LINES they are. It never rewrites or renumbers,
because CiteRef coordinates are indices into the full, unfiltered Page.lines
and every citation ever stored depends on those indices not moving.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from purser_ingest.chrome import chrome_line_indices

PAGE = [
    "                    InterGlobe Aviation Limited          ifly.SEP",
    "",
    "",
    "",
    "",
    "                    NOT A CONTROLLED COPY. DOWNLOADED FROM COMPANY PORTAL/ E-MANUAL",
    "        SAFETY AND EMERGENCY PROCEDURES MANUAL PART FOUR Section 4.2",
    "",
    "",
    "        Smoke/Fumes In The Cabin        Issue IX   Revision 00",
    "",
    "",
    "     SECTION 4.2",
    "     SMOKE/FUMES IN THE CABIN",
    "",
    " PART FOUR Section 4.2            Page 1 of 8      Effective 18 May 2023",
]


def test_identifies_every_furniture_line_and_nothing_else():
    assert chrome_line_indices(PAGE) == [0, 5, 6, 9, 15]


def test_real_content_is_never_marked_as_chrome():
    content = [
        "     When doors equipped with escape slides are opened for evacuation",
        "     Detach - Pull white detachment handle",
        "        Step 5- Brief 5 Able Bodied Passengers",
    ]
    assert chrome_line_indices(content) == []


def test_blank_lines_are_not_chrome():
    # A blank line inside a procedure is a paragraph break and carries meaning;
    # the reading view collapses runs of them, which is a different decision.
    assert chrome_line_indices(["", "   ", "\t"]) == []


needs_index = pytest.mark.skipif(
    not Path("data/manual.sqlite").is_file(), reason="needs the built index"
)


@needs_index
def test_corpus_wide_counts_match_the_measurement():
    """Guards against a pattern that silently eats real content.

    These numbers were measured before the module existed. If a future edit to
    the regex starts swallowing procedure text, the content count drops and this
    goes red. Without it, over-suppression is invisible -- the UI just quietly
    shows less of the manual than it used to.
    """
    con = sqlite3.connect("data/manual.sqlite")
    total = chrome = content = 0
    empty_pages = []
    for pdf_page, raw in con.execute("select pdf_page, lines from pages order by pdf_page"):
        lines = json.loads(raw)
        idx = set(chrome_line_indices(lines))
        total += len(lines)
        chrome += len(idx)
        kept = [i for i, s in enumerate(lines) if s.strip() and i not in idx]
        content += len(kept)
        if not kept:
            empty_pages.append(pdf_page)

    assert total == 49_723
    assert chrome == 6_100
    assert content == 24_276
    assert empty_pages == [314, 338, 484, 1179, 1181, 1182, 1185, 1188]
