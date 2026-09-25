from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

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
    chrome: list[int] = []  # indices into `lines` that are page furniture
    text: str  # lines joined, for FTS5 and embedding

    def content_lines(self) -> list[tuple[int, str]]:
        """(original index, text) for every non-blank, non-furniture line.

        The index is deliberately the ORIGINAL one. It is what CiteRef.line_from
        and line_to mean, and renumbering here would break every citation while
        still producing text that reads correctly.
        """
        skip = set(self.chrome)
        return [(i, s) for i, s in enumerate(self.lines) if s.strip() and i not in skip]


class Block(BaseModel):
    """One structural unit of the manual, recovered from the text layer.

    `text` is verbatim for every kind EXCEPT `para`, `bullet`, `step` and `note`, where
    lines the PDF hard-wrapped are rejoined with a single space (or none, after
    a line-end hyphen). That restores the sentence the author wrote; the line
    break at column 90 was a layout artifact, not meaning. `table` keeps its own
    newlines and leading spaces, because its columns ARE the information.

    `toc` is one row of a section's printed contents page: `text` is the entry's
    title alone, `number` its numbering ("2.1") and `page` the page in the
    section it points at. The dot leaders between them were typesetting.
    """

    kind: Literal[
        "heading", "subheading", "para", "bullet", "step", "note", "caption", "table", "toc"
    ]
    level: int = 0  # heading depth, bullet/step nesting, or toc entry depth
    text: str
    depth: int = 0  # enclosing headings -- see purser_core.outline.annotate_depth
    number: str | None = None  # toc only
    page: int | None = None  # toc only: a page_in_section


class PageText(BaseModel):
    """A page as handed to the agent: verbatim, with line numbers so it can cite."""

    pdf_page: int
    part: PartName
    section: str | None
    section_title: str | None
    page_in_section: int
    section_total: int  # so a windowed read never looks like the whole section
    numbered_lines: list[str]  # "12|CABIN CREW SHALL..." — index is the citable one


class ReadingPage(BaseModel):
    """One page of the manual, shaped for a person rather than the model."""

    pdf_page: int
    page_in_section: int
    section_total: int
    section: str | None
    section_title: str | None
    revision: str | None
    effective: date
    blocks: list[Block]
    empty: bool  # True for the 8 pages that carry no text at all
    # Headings still open at the top of this page, outermost first: the page
    # opens inside these sections, which began on an earlier page.
    continues: list[str] = []


class SectionHit(BaseModel):
    """One section that matched, with the pages inside it that did.

    `hit_pages` is not exhaustive: it holds only the pages absorbed into this
    section *before* the section-grouping walk in `PurserTools.search` had
    already found its k-th section and stopped. A section that had more
    matching pages further down the fused ranking will not have them listed
    here -- this is "pages that matched before the walk stopped," not every
    page of the section that matched.
    """

    part: PartName
    section: str | None  # None for unsectioned Parts and Annexures
    section_title: str | None
    score: float  # fused score of this section's best page
    hit_pages: list[int]  # pdf_page values, best-first
    hit_page_numbers: list[int]  # the corresponding page_in_section values
    snippet: str  # from the best-scoring page


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
