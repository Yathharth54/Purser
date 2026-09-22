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
    pages = assemble(extract_pages(PDF))
    by_section = defaultdict(list)
    for p in pages:
        if p.section:
            by_section[(p.part, p.section)].append(p.page_in_section)
    for key, nums in by_section.items():
        assert sorted(nums) == list(range(1, len(nums) + 1)), f"{key} has gaps: {sorted(nums)}"


@needs_pdf
def test_section_6_7_exits_is_fully_captured():
    """Regression: 'Effective18 May 2023' with no space dropped 53 of 60 pages."""
    pages = assemble(extract_pages(PDF))
    exits = [p for p in pages if p.section == "6.7"]
    assert len(exits) == 60


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
