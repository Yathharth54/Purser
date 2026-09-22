import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from purser_core.models import PartName
from purser_ingest.assemble import assemble
from purser_ingest.extract import extract_pages
from purser_ingest.headers import parse_header

PDF = Path(os.environ.get("PURSER_PDF_PATH", ""))
needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="manual PDF not present")


def test_parse_header_title_and_revision():
    line = "            Evacuations                 Issue IX      Revision 00"
    title, revision = parse_header(f"SAFETY AND EMERGENCY PROCEDURES MANUAL\n{line}\n")
    assert title == "Evacuations"
    assert revision == "Issue IX Revision 00"


def test_parse_header_reassembles_a_title_wrapped_across_the_revision_line():
    """pdftotext -layout interleaves a wrapped title's remainder AFTER the
    revision token, on the line below it. Real page 555 (§4.3)."""
    text = (
        "SAFETY AND EMERGENCY PROCEDURES MANUAL PART FOUR Section 4.3\n"
        "\n"
        "            Rapid and slow decompression (Pressurization\n"
        "                                                             Issue IX   Revision 00\n"
        "                             Problems)\n"
    )
    title, revision = parse_header(text)
    assert title == "Rapid and slow decompression (Pressurization Problems)"
    assert revision == "Issue IX Revision 00"


def test_parse_header_reassembles_a_second_wrapped_title():
    """Real page 421 (§3.9). The exact wrapped remainder is 'Boarding', not the
    'Disembarking/Embarking' guessed during review -- verified against the page."""
    text = (
        "SAFETY AND EMERGENCY PROCEDURES MANUAL PART THREE Section 3.9\n"
        "\n"
        "            Fuelling with Passengers On Board and or While\n"
        "                                                               Issue IX   Revision 00\n"
        "                               Boarding\n"
    )
    title, revision = parse_header(text)
    assert title == "Fuelling with Passengers On Board and or While Boarding"
    assert revision == "Issue IX Revision 00"


@needs_pdf
def test_every_page_resolves_to_a_coordinate():
    """The most important test in the project.

    A footer-parse failure does not crash anything — it produces a citation that
    points at the wrong page. That is the worst defect this app can ship.
    """
    pages = assemble(extract_pages(PDF))
    assert len(pages) == 1226
    seen_parts = {p.part for p in pages}
    missing = set(PartName) - seen_parts
    assert seen_parts == set(PartName), f"parts missing from the parse: {missing}"
    for p in pages:
        # >= 1 is live: a footer reading "Page 0 of 5" would trip it. The <= check
        # removed here can never fail -- PageCoord._within_section already
        # enforces it for every footer-parsed page, and the 4 fallback pages are
        # constructed to satisfy it by definition.
        assert p.page_in_section >= 1


@needs_pdf
def test_page_numbering_is_contiguous_within_each_section():
    """Within each section, page_in_section is a gapless, duplicate-free run.

    The run's maximum must equal section_total, and it must start at 1 or at 3 —
    the manual's own Part-level lead-in pages (2 unsectioned pages before a Part's
    first titled section) share that section's running page counter, so the first
    titled section of a Part starts its printed numbering at 3, not 1. Any other
    starting value is a genuine parse failure, not a document quirk, and must fail.
    """
    pages = assemble(extract_pages(PDF))
    by_section: dict[tuple, list[int]] = defaultdict(list)
    totals: dict[tuple, set[int]] = defaultdict(set)
    for p in pages:
        if p.section:
            key = (p.part, p.section)
            by_section[key].append(p.page_in_section)
            totals[key].add(p.section_total)
    for key, nums in by_section.items():
        s = sorted(nums)
        run = list(range(s[0], s[-1] + 1))
        assert s == run, f"{key} is not a contiguous run: {s}"
        assert s[-1] == max(totals[key]), (
            f"{key} run ends at {s[-1]} but section_total is {totals[key]}: {s}"
        )
        assert s[0] in (1, 3), f"{key} starts at {s[0]}, expected 1 or 3: {s}"


@needs_pdf
def test_section_6_7_exits_is_fully_captured():
    """Regression: 'Effective18 May 2023' with no space dropped 53 of 60 pages."""
    pages = assemble(extract_pages(PDF))
    exits = [p for p in pages if p.section == "6.7"]
    assert len(exits) == 60


@needs_pdf
def test_part_lead_in_pages_are_unsectioned():
    """Pin the five known Part lead-in blocks so this is documented, not rediscovered.

    Each of Parts One/Two/Three/Four/Six opens with 2 unsectioned title/TOC pages
    (footer reads e.g. "PART ONE Page 1 of 76", no Section token) before that Part's
    first titled section begins its own printed numbering at page 3.
    """
    pages = assemble(extract_pages(PDF))
    by_pdf_page = {p.pdf_page: p for p in pages}
    lead_in_pdf_pages = [27, 28, 141, 142, 195, 196, 523, 524, 749, 750]
    for pdf_page in lead_in_pdf_pages:
        p = by_pdf_page[pdf_page]
        assert p.section is None, f"pdf_page {pdf_page} expected section=None, got {p.section}"
        assert p.page_in_section in (1, 2), (
            f"pdf_page {pdf_page} expected page_in_section in (1, 2), got {p.page_in_section}"
        )


@needs_pdf
def test_known_section_boundaries():
    pages = assemble(extract_pages(PDF))
    evac = [p for p in pages if p.section == "4.4"]
    assert evac[0].pdf_page == 567
    assert evac[-1].pdf_page == 646
    assert evac[0].section_title == "Evacuations"


@needs_pdf
def test_all_37_section_titles_including_both_wrapped_ones():
    """§4.3 and §3.9 wrap across the revision line and were shipped truncated
    ('...Pressurization' with an unbalanced paren, '...and or While'). Pin the
    complete titles here, and every other section's title alongside them, so a
    future header-parsing change cannot silently truncate any of the 37 again."""
    pages = assemble(extract_pages(PDF))
    first_title = {}
    for p in pages:
        if p.section and p.section not in first_title:
            first_title[p.section] = p.section_title

    expected = {
        "1.1": "Regulatory Overview",
        "1.2": "Aviation Terminology",
        "1.3": "Theory of Flight",
        "1.4": "Physiology of Flight",
        "2.1": "Air Operator",
        "2.2": "Crew Members",
        "2.3": "DGCA Inspectors",
        "3.1": "Common Terminology",
        "3.2": "Crew Co-ordination and Communication",
        "3.3": "Briefings",
        "3.4": "Safety Checks",
        "3.5": "Passenger Handling",
        "3.6": "Passenger and Crew Member Seats and Restraints",
        "3.7": "Carry – On Baggage",
        "3.8": "Electronic devices",
        "3.9": "Fuelling with Passengers On Board and or While Boarding",
        "3.10": "Pre Take Off and Pre Landing",
        "3.11": "Apron Safety",
        "3.12": "Turbulence",
        "3.13": "Crew Member Incapacitation",
        "3.14": "Flight Deck Protocol",
        "3.15": "Fuel Dumping",
        "3.16": "Post Flight Duties",
        "3.17": "Oxygen Administration",
        "4.1": "Fire Fighting",
        "4.2": "Smoke/Fumes In The Cabin",
        "4.3": "Rapid and slow decompression (Pressurization Problems)",
        "4.4": "Evacuations",
        "5.1": "Emergency Equipment",
        "6.1": "PHYSICAL DESCRIPTION",
        "6.2": "GALLEYS",
        "6.3": "Communication Systems",
        "6.4": "Lighting Systems",
        "6.5": "Water and Waste Systems",
        "6.6": "Air Conditioning and Ventilation systems",
        "6.7": "Exits",
        "6.8": "Unique Features",
    }
    assert len(expected) == 37
    assert first_title == expected


@needs_pdf
def test_front_matter_effective_date_is_derived_from_a_real_footer():
    """Pages 1-4 carry no footer of their own; their effective date must come
    from the manual's own parsed data, not a literal that goes stale on the
    next revision."""
    pages = assemble(extract_pages(PDF))
    front = [p for p in pages if p.pdf_page <= 4]
    assert len(front) == 4
    first_footer_bearing = next(p for p in pages if p.pdf_page > 4)
    for p in front:
        assert p.effective == first_footer_bearing.effective


def test_front_matter_effective_date_is_derived_not_hardcoded():
    """Synthetic, PDF-free version of the same guarantee: fabricate a manual
    whose real effective date is nothing like the old hardcoded 2023-05-18."""
    raw_pages = ["cover, no footer\n"] * 4 + [
        "PART ONE Section 1.1   Page 3 of 76   Effective 08 October 2025\n"
    ]
    pages = assemble(raw_pages)
    front = [p for p in pages if p.pdf_page <= 4]
    assert len(front) == 4
    for p in front:
        assert p.effective == date(2025, 10, 8)


def test_front_matter_title_is_consistent_across_the_whole_block():
    """Pages 1-4 (no footer) got 'Manual Administration' while pages 5-26 (which
    DO parse a Front Matter footer) got None -- a TOC node spanning pp.1-26
    should not advertise a title that only describes 4 of those 22 pages."""
    raw_pages = ["cover, no footer\n"] * 2 + [
        "LOC 1 of 2   Effective 08 October 2025\n",
        "LOC 2 of 2   Effective 08 October 2025\n",
    ]
    pages = assemble(raw_pages)
    assert {p.section_title for p in pages} == {"Manual Administration"}


@needs_pdf
def test_page_text_is_lines_joined_for_every_page():
    """Page.text is documented as 'lines joined'. Phase 2 splices verbatim quote
    text out of `lines` and requires the two to agree byte-for-byte."""
    pages = assemble(extract_pages(PDF))
    for p in pages:
        assert p.text == "\n".join(p.lines)


def test_assemble_names_the_page_on_parse_failure():
    """A footer whose part name isn't in PartName must fail loudly, naming the page."""
    good_footer = "PART SIX Section 6.1   Page 1 of 5   Effective 18 May 2023"
    bad_footer = "PART ELEVEN Section 11.1   Page 1 of 5   Effective 18 May 2023"
    raw_pages = [f"some content\n{good_footer}\n", f"some content\n{bad_footer}\n"]
    with pytest.raises(Exception) as exc_info:
        assemble(raw_pages)
    message = str(exc_info.value)
    assert re.search(r"\bpage 2\b", message), f"expected 'page 2' anchored in message: {message!r}"
    assert bad_footer in message or "PART ELEVEN" in message
