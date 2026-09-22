import os
from collections import defaultdict
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


@needs_pdf
def test_every_page_resolves_to_a_coordinate():
    """The most important test in the project.

    A footer-parse failure does not crash anything — it produces a citation that
    points at the wrong page. That is the worst defect this app can ship.
    """
    pages = assemble(extract_pages(PDF))
    assert len(pages) == 1226
    for p in pages:
        assert p.part in PartName
        assert p.page_in_section >= 1
        assert p.page_in_section <= p.section_total


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


def test_assemble_names_the_page_on_parse_failure():
    """A footer whose part name isn't in PartName must fail loudly, naming the page."""
    good_footer = "PART SIX Section 6.1   Page 1 of 5   Effective 18 May 2023"
    bad_footer = "PART ELEVEN Section 11.1   Page 1 of 5   Effective 18 May 2023"
    raw_pages = [f"some content\n{good_footer}\n", f"some content\n{bad_footer}\n"]
    with pytest.raises(Exception) as exc_info:
        assemble(raw_pages)
    message = str(exc_info.value)
    assert "2" in message
    assert bad_footer in message or "PART ELEVEN" in message
