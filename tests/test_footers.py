from datetime import date

import pytest

from purser_core.models import PartName
from purser_ingest.footers import parse_footer


def test_section_footer():
    c = parse_footer("PART FOUR Section 4.4      Page 34 of 80      Effective 18 May 2023")
    assert c.part is PartName.FOUR
    assert c.section == "4.4"
    assert c.page_in_section == 34
    assert c.section_total == 80
    assert c.effective == date(2023, 5, 18)


def test_missing_space_after_effective():
    """53 pages in section 6.7 print 'Effective18 May 2023' with no space."""
    c = parse_footer("PART SIX Section 6.7      Page 9 of 60      Effective18 May 2023")
    assert c.section == "6.7"
    assert c.effective == date(2023, 5, 18)


def test_part_footer_without_section():
    c = parse_footer("PART SEVEN            Page 12 of 122        Effective 18 May 2023")
    assert c.part is PartName.SEVEN
    assert c.section is None
    assert c.page_in_section == 12


def test_annexure_footer():
    c = parse_footer("Annexures        Page 9 of 30   Effective 29 April 2025")
    assert c.part is PartName.ANNEX


def test_front_matter_footer_omits_the_word_page():
    c = parse_footer("LOC 2 of 4      Effective 29 September 2025")
    assert c.part is PartName.FRONT
    assert c.page_in_section == 2
    assert c.section_total == 4


def test_last_footer_wins():
    """Sparse pages repeat the header block; the final footer is authoritative."""
    text = (
        "PART SIX Section 6.6   Page 3 of 10   Effective 18 May 2023\n"
        "INTENTIONALLY LEFT BLANK\n"
        "PART SIX Section 6.6   Page 4 of 10   Effective 18 May 2023\n"
    )
    assert parse_footer(text).page_in_section == 4


def test_no_footer_returns_none():
    assert parse_footer("InterGlobe Aviation Limited\nifly.SEP") is None


def test_page_beyond_section_length_is_rejected():
    with pytest.raises(ValueError):
        parse_footer("PART ONE Section 1.1   Page 99 of 12   Effective 18 May 2023")


def test_body_cross_reference_after_the_real_footer_does_not_win():
    """A stray footer-shaped cross-reference positioned before the true footer,
    outside the footer window, must not be selected instead of it. SEC is tried
    before FRONT (see `_PATTERNS`), so without the window a SEC-shaped decoy in
    the body wins over the FRONT-shaped real footer -- proving the window (not
    just 'last match wins') is what makes this page resolve correctly."""
    text = (
        "See PART THREE Section 3.5      Page 7 of 104      Effective 18 May 2023\n"
        + "INTENTIONALLY LEFT BLANK\n" * 6
        + "LOC 2 of 4      Effective 29 September 2025\n"
    )
    c = parse_footer(text)
    assert c.part is PartName.FRONT
    assert c.page_in_section == 2


def test_body_cross_reference_embedded_in_a_sentence_is_never_a_footer():
    """The $ anchor rejects a footer-shaped fragment that is not alone on its
    line -- a cross-reference woven into a sentence must never win, regardless
    of the footer window, because it never ends the line it sits on."""
    text = (
        "PART THREE Section 3.5      Page 34 of 104      Effective 18 May 2023\n"
        "See also cf. PART THREE Section 3.5 Page 7 of 104 Effective 18 May 2023"
        " for the checklist.\n"
    )
    c = parse_footer(text)
    assert c.section == "3.5"
    assert c.page_in_section == 34
