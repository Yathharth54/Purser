from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field

from purser_core.models import Block, PartName


class Citation(BaseModel):
    """What the client receives. Unlike CiteRef, this carries verbatim text --
    spliced by the backend, never written by the model."""

    pdf_page: int
    part: PartName
    section: str | None
    section_title: str | None
    page_in_section: int
    revision: str | None
    effective: date
    text: str
    blocks: list[Block] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        if self.section:
            return f"{self.part} §{self.section} p.{self.page_in_section}"
        return f"{self.part} p.{self.page_in_section}"


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str = Field(min_length=1)


class ThreadSummary(BaseModel):
    id: str
    title: str
    updated_at: str
