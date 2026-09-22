from datetime import date

from purser_core.models import Page, PartName
from purser_ingest.glossary_miner import mine_glossary


def _page(pdf_page, lines):
    return Page(
        pdf_page=pdf_page, part=PartName.ONE, section="1.2",
        section_title="Aviation Terminology", page_in_section=1, section_total=20,
        effective=date(2023, 5, 18), revision=None, lines=lines, text="\n".join(lines),
    )


def test_mines_two_column_abbreviation_table():
    page = _page(121, [
        "  ABP – Able Bodied Passenger                  PAX – Passenger",
        "  CIDS – Cabin Inter- Communication Data       ECAM – Electronic Centralized Aircraft",
    ])
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["ABP"] == "Able Bodied Passenger"
    assert entries["PAX"] == "Passenger"
    assert entries["ECAM"].startswith("Electronic Centralized Aircraft")


def test_mines_prose_term_definitions():
    page = _page(108, [
        "TIME ZONE: Is a region of the earth that has adopted the same standard time.",
    ])
    entries = {e.term: e.definition for e in mine_glossary([page])}
    assert entries["TIME ZONE"].startswith("Is a region of the earth")


def test_records_source_page_so_definitions_are_citable():
    page = _page(121, ["  PBE – Protective Breathing Equipment"])
    assert mine_glossary([page])[0].pdf_page == 121


def test_ignores_pages_outside_the_terminology_sections():
    page = Page(
        pdf_page=600, part=PartName.FOUR, section="4.4", section_title="Evacuations",
        page_in_section=34, section_total=80, effective=date(2023, 5, 18), revision=None,
        lines=["ABP – this is body text, not a glossary"], text="x",
    )
    assert mine_glossary([page]) == []
