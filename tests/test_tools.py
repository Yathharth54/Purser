import re
from pathlib import Path

import pytest

from purser_core.models import PartName
from purser_core.tools import _SNIPPET_CHARS, PurserTools

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def tools():
    return PurserTools("data")


def test_search_returns_hits_with_section_coordinates(tools):
    # `h.part` is a StrEnum (always truthy) and `hit_pages` is non-empty by
    # construction (_SectionAccum always seeds it with one page) -- neither
    # of those could ever fail. Assert something that actually pins the
    # coordinates instead: every hit_pages value is a real pdf_page, and the
    # snippet has real, bounded content.
    hits = tools.search("ditching", k=5)
    assert hits
    h = hits[0]
    assert isinstance(h.part, PartName)
    assert all(1 <= p <= 1226 for p in h.hit_pages)
    assert 0 < len(h.snippet) <= _SNIPPET_CHARS


def test_search_snippet_is_short_not_a_whole_page(tools):
    """search() is a locator. Reading is a separate, explicit act."""
    for hit in tools.search("evacuation", k=5):
        assert len(hit.snippet) <= _SNIPPET_CHARS


def test_search_k_is_an_upper_bound_on_sections_returned(tools):
    """k is the number of SECTIONS now, not pages — see design doc §8.4."""
    assert len(tools.search("evacuation", k=3)) <= 3


# --- Section-grouping algorithm, pinned against a controlled fused ranking ---
#
# These monkeypatch `rrf` so the exact page ranking handed to the grouping
# walk is under test control, independent of what the lexical/semantic lanes
# actually rank for a given query today. `corpus.page()` is real, so the
# part/section/page_in_section on each hit are genuine manual coordinates.


def _set_fused(monkeypatch, fused):
    monkeypatch.setattr("purser_core.tools.rrf", lambda *a, **kw: fused)


def test_repeated_section_yields_one_hit_with_several_pages_best_first(tools, monkeypatch):
    # 283, 284, 285 are all section "3.5"; 568 is section "4.4".
    _set_fused(monkeypatch, [(283, 10.0), (568, 9.0), (284, 8.0), (285, 7.0)])
    hits = tools.search("irrelevant", k=5)

    by_section = {h.section: h for h in hits}
    assert set(by_section) == {"3.5", "4.4"}
    assert by_section["3.5"].hit_pages == [283, 284, 285]
    assert by_section["4.4"].hit_pages == [568]


def test_hit_pages_capped_at_five(tools, monkeypatch):
    # Seven consecutive hits in section "3.5", then one in "4.4". Requesting
    # k=2 sections must not stop after the first page of "3.5" — the walk
    # keeps absorbing "3.5" duplicates (up to the cap) until a *second*
    # distinct section shows up.
    fused = [
        (283, 10.0),
        (284, 9.0),
        (285, 8.0),
        (286, 7.0),
        (287, 6.0),
        (288, 5.0),
        (289, 4.0),
        (568, 3.0),
    ]
    _set_fused(monkeypatch, fused)
    hits = tools.search("irrelevant", k=2)

    by_section = {h.section: h for h in hits}
    assert len(by_section["3.5"].hit_pages) == 5
    assert by_section["3.5"].hit_pages == [283, 284, 285, 286, 287]
    assert by_section["4.4"].hit_pages == [568]


def test_sections_ordered_by_score_descending_not_insertion_order(tools, monkeypatch):
    # "3.5" (pdf_page 283) is scanned FIRST but scores lower than "4.4"
    # (pdf_page 568), scanned second. The returned order must follow score,
    # not the order sections were first encountered.
    _set_fused(monkeypatch, [(283, 5.0), (568, 9.0)])
    hits = tools.search("irrelevant", k=2)

    assert [h.section for h in hits] == ["4.4", "3.5"]
    assert [h.score for h in hits] == [9.0, 5.0]


def test_unsectioned_part_is_preserved_not_dropped(tools, monkeypatch):
    # pdf_page 1 is a Front Matter lead-in page: section=None.
    _set_fused(monkeypatch, [(1, 4.0)])
    hits = tools.search("irrelevant", k=1)

    assert len(hits) == 1
    assert hits[0].section is None
    assert hits[0].part is PartName.FRONT


def test_k_controls_number_of_sections_not_pages(tools, monkeypatch):
    # Five pages, five distinct sections. k=2 must stop the walk after the
    # second distinct section even though three more pages remain unscanned.
    fused = [(1, 5.0), (29, 4.0), (283, 3.0), (567, 2.0), (600, 1.0)]
    _set_fused(monkeypatch, fused)
    hits = tools.search("irrelevant", k=2)

    assert len(hits) == 2
    assert [h.section for h in hits] == [None, "1.1"]


def test_read_section_returns_numbered_lines_in_order(tools):
    pages = tools.read_section("4.4", page_from=30, page_to=32)
    assert [p.page_in_section for p in pages] == [30, 31, 32]
    # numbered_lines are ordered and start with a valid index (not necessarily 0,
    # since furniture lines are dropped)
    assert pages[0].numbered_lines
    assert re.match(r"^\d+\|", pages[0].numbered_lines[0])


def test_read_section_clamps_out_of_range_requests(tools):
    pages = tools.read_section("4.4", page_from=78, page_to=999)
    assert pages[-1].page_in_section == 80


def test_read_section_default_range_covers_a_lead_in_offset_section(tools):
    """Section 1.1 opens at page_in_section 3 (Part One has a 2-page lead-in) and
    has 74 rows in the database, but its true last page is page_in_section 76 —
    len(pages) (74) is NOT the upper clamp bound, max(page_in_section) (76) is.

    A read_section that clamped against len(pages) instead of the section's
    actual page_in_section range would silently drop pages 75 and 76 from the
    default (whole-section) read. This pins that down against the real index.
    """
    pages = tools.read_section("1.1")
    assert [p.page_in_section for p in pages][0] == 3
    assert [p.page_in_section for p in pages][-1] == 76
    assert len(pages) == 74


def test_read_section_clamps_high_end_of_lead_in_offset_section(tools):
    """Requesting far beyond the end of an offset section must clamp to that
    section's real last page (76), not to its row count (74)."""
    pages = tools.read_section("1.1", page_from=1, page_to=999)
    assert pages[-1].page_in_section == 76


def test_read_page_includes_neighbours(tools):
    pages = tools.read_page(600, before=1, after=1)
    assert [p.pdf_page for p in pages] == [599, 600, 601]


def test_read_page_skips_out_of_range_neighbours_silently(tools):
    """Page 1 has no page 0; asking for a neighbour before it must not raise."""
    pages = tools.read_page(1, before=5, after=0)
    assert [p.pdf_page for p in pages] == [1]


def test_toc_lists_every_numbered_section(tools):
    assert len([n for n in tools.toc() if n.section]) == 37


def test_toc_filters_by_part(tools):
    """Filtering by Part keeps every node of that Part, including the
    section=None lead-in: Part Four opens with an unsectioned 2-page lead-in
    (pdf_page_from 523) before its four numbered sections begin. Those pages
    are real content, so they belong in "what Part Four contains" — dropping
    them would be inferring a section boundary the manual's own footers don't
    give us, which this project never does.
    """
    from purser_core.models import PartName

    nodes = tools.toc(part=PartName.FOUR)
    assert all(n.part is PartName.FOUR for n in nodes)
    assert {n.section for n in nodes} == {None, "4.1", "4.2", "4.3", "4.4"}

    lead_ins = [n for n in nodes if n.section is None]
    assert len(lead_ins) == 1
    assert lead_ins[0].pdf_page_from == 523


def test_lookup_term_returns_the_manuals_own_definition(tools):
    entry = tools.lookup_term("PAX")
    assert entry is not None and entry.definition == "Passenger"


def test_lookup_term_unknown_returns_none(tools):
    assert tools.lookup_term("zzzz") is None


# --- The one thing that matters most in this task ---
#
# numbered_lines is the substrate for every citation the finished app will ever
# show. The number printed before "|" in each entry MUST equal that line's
# index in Page.lines (0-based), because a later layer slices
# Page.lines[line_from:line_to] using numbers an agent read off numbered_lines.
# A silent off-by-one here shifts every quote in the whole application by one
# line while still looking completely plausible.


def test_numbered_lines_index_matches_page_lines_index_exactly(tools):
    """Each numbered_line's index addresses the correct line in Page.lines.

    After the furniture-removal change, numbered_lines is shorter than page.lines,
    but each index still addresses the original line. The indices are NOT renumbered.
    """
    pdf_page = 600
    page = tools.corpus.page(pdf_page)
    (page_text,) = tools.read_page(pdf_page)

    # numbered_lines now contains only content lines, so it's shorter.
    assert len(page_text.numbered_lines) == len(page.content_lines())

    for entry, (expected_line_no, expected_text) in zip(
        page_text.numbered_lines, page.content_lines(), strict=True
    ):
        match = re.match(r"^(\d+)\|(.*)$", entry, re.DOTALL)
        assert match, f"malformed numbered_line entry: {entry!r}"
        line_no, text = int(match.group(1)), match.group(2)
        # The printed index must match the original index from content_lines()
        assert line_no == expected_line_no
        assert text == expected_text
        assert page.lines[line_no] == expected_text, (
            f"numbered_lines index {line_no} does not address the same text in Page.lines"
        )


def test_numbered_lines_omit_furniture_but_keep_original_numbers(tools):
    """The agent should never see letterhead, and never cite a shifted index.

    Before this, ~51% of every page handed to the model was blank lines and
    repeated boilerplate. It cost context and it produced citations pointing at
    'InterGlobe Aviation Limited'.
    """
    [pt] = tools.read_page(600)
    assert pt.numbered_lines, "page 600 has content"
    assert not any("InterGlobe" in s for s in pt.numbered_lines)
    assert not any("NOT A CONTROLLED COPY" in s for s in pt.numbered_lines)
    assert not any("Page 1 of" in s for s in pt.numbered_lines)

    page = tools.corpus.page(600)
    for entry in pt.numbered_lines:
        num, _, text = entry.partition("|")
        assert page.lines[int(num)] == text


def test_a_page_of_pure_furniture_yields_no_lines(tools):
    # pdf_page 314 is one of exactly 8 pages that carry no content at all.
    [pt] = tools.read_page(314)
    assert pt.numbered_lines == []


# --- the agent reads in bounded windows --------------------------------------


def test_read_section_can_be_capped_to_a_window_of_pages(tools):
    """An uncapped read of section 4.4 hands the model all 80 pages, and every
    later turn re-sends them: one ditching question measured 454k input tokens."""
    assert [p.page_in_section for p in tools.read_section("4.4", max_pages=6)] == [1, 2, 3, 4, 5, 6]
    window = tools.read_section("4.4", page_from=30, page_to=80, max_pages=6)
    assert [p.page_in_section for p in window] == [30, 31, 32, 33, 34, 35]


def test_read_page_neighbours_can_be_capped(tools):
    pages = tools.read_page(600, before=10, after=10, max_pages=7)
    assert [p.pdf_page for p in pages] == [597, 598, 599, 600, 601, 602, 603]


def test_a_page_tells_the_model_how_long_its_section_is(tools):
    """Without the total, a capped read looks like the whole section."""
    [pt] = tools.read_page(600)
    assert (pt.page_in_section, pt.section_total) == (34, 80)
