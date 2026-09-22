from datetime import date

from purser_core.models import Page, PartName
from purser_ingest.glossary_miner import mine_glossary


def _page(pdf_page, lines):
    return Page(
        pdf_page=pdf_page,
        part=PartName.ONE,
        section="1.2",
        section_title="Aviation Terminology",
        page_in_section=1,
        section_total=20,
        effective=date(2023, 5, 18),
        revision=None,
        lines=lines,
        text="\n".join(lines),
    )


def test_mines_two_column_abbreviation_table():
    page = _page(
        121,
        [
            "  ABP – Able Bodied Passenger                  PAX – Passenger",
            "  CIDS – Cabin Inter- Communication Data       ECAM – Electronic Centralized Aircraft",
            "  System                                       Monitoring",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["ABP"] == "Able Bodied Passenger"
    assert entries["PAX"] == "Passenger"
    # Genuine source text -- the mid-word hyphen in "Inter-" is not a typo to fix.
    assert entries["CIDS"] == "Cabin Inter- Communication Data System"
    assert entries["ECAM"] == "Electronic Centralized Aircraft Monitoring"


def test_mines_prose_term_definitions():
    page = _page(
        108,
        [
            "TIME ZONE: Is a region of the earth that has adopted the same standard time.",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["TIME ZONE"].startswith("Is a region of the earth")


def test_records_source_page_so_definitions_are_citable():
    page = _page(121, ["  PBE – Protective Breathing Equipment"])
    assert mine_glossary([page])[0].pdf_page == 121


def test_ignores_pages_outside_the_terminology_sections():
    page = Page(
        pdf_page=600,
        part=PartName.FOUR,
        section="4.4",
        section_title="Evacuations",
        page_in_section=34,
        section_total=80,
        effective=date(2023, 5, 18),
        revision=None,
        lines=["ABP – this is body text, not a glossary"],
        text="x",
    )
    assert mine_glossary([page]) == []


def test_merges_multiline_prose_definition():
    page = _page(
        107,
        [
            "     CABIN CREW: A crew member other than a flight crew member detailed to carry out",
            "     such duties as may be assigned, in the interests of safety of the passengers, by",
            "     the operator or the pilot in command of the aircraft.",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["CABIN CREW"] == (
        "A crew member other than a flight crew member detailed to carry out such duties "
        "as may be assigned, in the interests of safety of the passengers, by the operator "
        "or the pilot in command of the aircraft."
    )


def test_merge_stops_at_blank_line():
    page = _page(
        108,
        [
            "TIME ZONE: Is a region of the earth that has adopted",
            "the same standard time.",
            "",
            "This line must not be appended to the definition above.",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["TIME ZONE"] == (
        "Is a region of the earth that has adopted the same standard time."
    )


def test_merge_stops_at_next_term_definition():
    page = _page(
        107,
        [
            "CABIN CREW: A crew member other than a flight crew member detailed to carry out",
            "such duties as may be assigned.",
            "SENIOR CABIN CREW: The Senior Cabin Crew is a senior cabin crew who has overall",
            "responsibility for cabin safety.",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["CABIN CREW"] == (
        "A crew member other than a flight crew member detailed to carry out such duties "
        "as may be assigned."
    )
    assert entries["SENIOR CABIN CREW"] == (
        "The Senior Cabin Crew is a senior cabin crew who has overall responsibility for "
        "cabin safety."
    )


def test_rejects_note_markers():
    page = _page(
        211,
        [
            "NOTE1: If the preceding duty period exceeds 18 hours, then the rest period shall "
            "include a local night.",
            "NOTE2: Period of transportation shall not be counted towards duty time.",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert "NOTE1" not in entries
    assert "NOTE2" not in entries


def test_rejects_single_letter_terms():
    page = _page(119, ["      P – Papa"])
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert "P" not in entries


def test_abbreviation_table_columns_not_merged_across_rows():
    page = _page(
        121,
        [
            "  ABP – Able Bodied Passenger                  PAX – Passenger",
            "  PBE – Protective Breathing Equipment         CIDS – Cabin Inter- Communication Data",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["ABP"] == "Able Bodied Passenger"
    assert entries["PAX"] == "Passenger"
    assert entries["PBE"] == "Protective Breathing Equipment"
    assert entries["CIDS"] == "Cabin Inter- Communication Data"


def test_malformed_abbreviation_row_does_not_corrupt_the_open_entry_in_its_column():
    """Real page 121: 'FAP-Flight Attendant Panel' has no space around its hyphen,
    so it never matches the abbreviation grammar -- but it must not be silently
    absorbed as a continuation of whatever entry is still open in its column."""
    page = _page(
        121,
        [
            "  EMER – Emergency                                  UMNR – Unaccompanied Minor",
            "  FAP-Flight Attendant Panel",
        ],
    )
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["EMER"] == "Emergency"
    assert entries["UMNR"] == "Unaccompanied Minor"
    assert "FAP" not in entries
