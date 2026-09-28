"""The MCP surface: Purser's five reading tools plus `ask`.

A thin adapter. Every tool delegates to the singletons the PWA's API already
uses (purser_api.deps), so the two surfaces can never disagree about the
manual. Imported only on the first /mcp request -- see purser_mcp.http.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from purser_agent import tooling
from purser_api.citations import resolve_all
from purser_api.deps import get_agent, get_corpus, get_deps, get_tools
from purser_api.schemas import Citation
from purser_core.models import GlossaryEntry, PageText, PartName, SectionHit, TocNode

LAST_PAGE = 1226

INSTRUCTIONS = """Purser reads the Airbus A320/321 Safety and Emergency Procedures
Manual. Every page is addressed as PART, section and page, e.g. PART FOUR §4.4 p.34.

When you answer from these tools, quote the manual's lines verbatim and cite each
quote by its coordinates. Never paraphrase a procedure, a command or a drill: crew
act on the exact words. If the tools do not turn up the answer, say plainly that
the manual does not cover it rather than filling the gap.

Start with `search` (or `lookup_term` for an acronym), then read the candidate
with `read_section` or `read_page`. `ask` returns Purser's own cited answer in one
call."""

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


class AskResult(BaseModel):
    """Purser's answer. `citations[].text` is spliced from the index, never model-written."""

    body: str
    not_in_manual: bool
    citations: list[Citation]


def build_server() -> MCPServer:
    """A fresh server. purser_mcp.http builds a new one whenever its event loop changes."""
    server = MCPServer("purser", instructions=INSTRUCTIONS)

    @server.tool(description=tooling.SEARCH, annotations=_READ_ONLY)
    def search(query: str, k: int = 8) -> list[SectionHit]:
        return get_tools().search(query, k=k)

    @server.tool(description=tooling.TOC, annotations=_READ_ONLY)
    def toc(part: PartName | None = None) -> list[TocNode]:
        return get_tools().toc(part=part)

    @server.tool(description=tooling.READ_SECTION, annotations=_READ_ONLY)
    def read_section(
        section: str, page_from: int = 1, page_to: int | None = None
    ) -> list[PageText]:
        pages = get_tools().read_section(
            section, page_from=page_from, page_to=page_to, max_pages=tooling.MAX_READ_PAGES
        )
        if not pages:
            raise ToolError(
                f"No pages for section {section!r} in that range. "
                "Call toc for the manual's section numbers, or read_page for unsectioned pages."
            )
        return pages

    @server.tool(description=tooling.READ_PAGE, annotations=_READ_ONLY)
    def read_page(pdf_page: int, before: int = 0, after: int = 0) -> list[PageText]:
        if not 1 <= pdf_page <= LAST_PAGE:
            raise ToolError(f"pdf_page must be between 1 and {LAST_PAGE}, got {pdf_page}.")
        return get_tools().read_page(
            pdf_page, before=before, after=after, max_pages=tooling.MAX_READ_PAGES
        )

    @server.tool(description=tooling.LOOKUP_TERM, annotations=_READ_ONLY)
    def lookup_term(term: str) -> GlossaryEntry | None:
        return get_tools().lookup_term(term)

    @server.tool(description=tooling.ASK)
    async def ask(question: str) -> AskResult:
        try:
            result = await get_agent().run(question, deps=get_deps())
        except Exception as exc:  # a missing key, a provider outage, a bad model reply
            raise ToolError(f"Purser could not answer: {exc}") from exc
        answer = result.output
        citations = resolve_all(get_corpus(), answer.refs)
        # `blocks` only draws a quote in the PWA; `text` is the quote itself.
        return AskResult(
            body=answer.body,
            not_in_manual=answer.not_in_manual,
            citations=[c.model_copy(update={"blocks": []}) for c in citations],
        )

    return server
