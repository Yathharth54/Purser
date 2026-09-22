from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, model_validator


class PartName(StrEnum):
    ONE = "PART ONE"
    TWO = "PART TWO"
    THREE = "PART THREE"
    FOUR = "PART FOUR"
    FIVE = "PART FIVE"
    SIX = "PART SIX"
    SEVEN = "PART SEVEN"
    EIGHT = "PART EIGHT"
    NINE = "PART NINE"
    TEN = "PART TEN"
    ANNEX = "Annexures"
    FRONT = "Front Matter"


class PageCoord(BaseModel):
    """Where a page sits in the manual, parsed from its own footer."""

    part: PartName
    section: str | None = None
    page_in_section: int
    section_total: int
    effective: date

    @model_validator(mode="after")
    def _within_section(self) -> PageCoord:
        if self.page_in_section > self.section_total:
            raise ValueError(
                f"page {self.page_in_section} beyond section length {self.section_total}"
            )
        return self


class Page(BaseModel):
    """One physical page of the manual."""

    pdf_page: int  # 1..1226 — what the renderer needs
    part: PartName
    section: str | None
    section_title: str | None
    page_in_section: int  # what she flips to
    section_total: int
    effective: date
    revision: str | None
    lines: list[str]  # verbatim, 0-indexed — the citation substrate
    text: str  # lines joined, for FTS5 and embedding


class PageText(BaseModel):
    """A page as handed to the agent: verbatim, with line numbers so it can cite."""

    pdf_page: int
    part: PartName
    section: str | None
    section_title: str | None
    page_in_section: int
    numbered_lines: list[str]  # "12| CABIN CREW SHALL..." — index is the citable one


class SearchHit(BaseModel):
    pdf_page: int
    part: PartName
    section: str | None
    section_title: str | None
    page_in_section: int
    snippet: str
    score: float


class TocNode(BaseModel):
    part: PartName
    section: str | None
    title: str | None
    pdf_page_from: int
    pdf_page_to: int
    pages: int


class GlossaryEntry(BaseModel):
    term: str
    definition: str
    aliases: list[str] = []
    pdf_page: int
