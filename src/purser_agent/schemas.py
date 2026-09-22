from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CiteRef(BaseModel):
    """A pointer into the manual. Deliberately carries NO quote text.

    The model is never allowed to write quote text: it emits only
    coordinates (a page number and a half-open line range), and a later
    layer (purser_api/citations.py) splices the verbatim text out of the
    index. That makes quotes correct by construction, not by validation --
    paraphrasing a procedure is not a mistake the model can make, because
    there is no `quote` or `text` field for it to write one into. Do not
    add one "for convenience"; that would reopen exactly the failure mode
    this schema exists to close.
    """

    pdf_page: int = Field(ge=1, le=1226, description="Physical page number in the PDF, 1-1226")
    line_from: int = Field(ge=0, description="First line, 0-indexed, inclusive")
    line_to: int = Field(ge=1, description="Last line, 0-indexed, EXCLUSIVE")

    @model_validator(mode="after")
    def _non_empty_range(self) -> CiteRef:
        if self.line_to <= self.line_from:
            raise ValueError("line_to must be greater than line_from (half-open range)")
        return self


class Answer(BaseModel):
    """What the agent returns. Backstop validation only -- the schema is the mechanism."""

    body: str = Field(description="Concise framing in the crew member's own language")
    refs: list[CiteRef] = Field(default_factory=list)
    not_in_manual: bool = False

    @model_validator(mode="after")
    def _claims_require_citations(self) -> Answer:
        if self.body.strip() and not self.refs and not self.not_in_manual:
            raise ValueError("answer makes claims without a citation")
        return self
