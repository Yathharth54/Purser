from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from purser_agent.prompts import SYSTEM_PROMPT
from purser_agent.provider import require_credentials, resolve_model
from purser_agent.schemas import Answer
from purser_core.models import GlossaryEntry, PageText, PartName, SectionHit, TocNode
from purser_core.tools import PurserTools

# The most pages one read hands the model. An uncapped read_section returned
# whole sections (4.4 is 80 pages) and every later turn re-sent them: one
# ditching question measured 454k input tokens over 16 model calls.
MAX_READ_PAGES = 6


@dataclass
class PurserDeps:
    """Everything the backend already knows. Never made a tool call."""

    tools: PurserTools


def build_agent(tools: PurserTools) -> Agent[PurserDeps, Answer]:
    # Fail here, naming the missing variable, rather than as an opaque 401
    # mid-stream while she is waiting on an answer.
    require_credentials()

    agent = Agent(
        resolve_model(),
        deps_type=PurserDeps,
        output_type=Answer,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )

    @agent.tool
    def search(ctx: RunContext[PurserDeps], query: str, k: int = 8) -> list[SectionHit]:
        """Find candidate sections of the manual for a topic.

        Returns up to `k` sections, best-scored first, each with the pages inside
        it that matched (`hit_pages`) and a `snippet` from the best of them. This
        NARROWS the search space -- it does not tell you which candidate is
        correct. The right section is first only ~62% of the time and can be
        anywhere in the returned list. Read every candidate's section_title and
        snippet and judge which one actually answers the question before opening
        it with read_section/read_page.
        """
        return ctx.deps.tools.search(query, k=k)

    @agent.tool
    def toc(ctx: RunContext[PurserDeps], part: PartName | None = None) -> list[TocNode]:
        """List the manual's Parts and Sections, optionally within one Part."""
        return ctx.deps.tools.toc(part=part)

    @agent.tool
    def read_section(
        ctx: RunContext[PurserDeps],
        section: str,
        page_from: int = 1,
        page_to: int | None = None,
    ) -> list[PageText]:
        """Read verbatim numbered lines from a section, e.g. section='4.4'.

        Returns at most 6 pages per call, starting at `page_from` (a
        page_in_section number). Each page carries `section_total`; to read
        further, call again with a later `page_from`. Start where search found
        the topic -- its `hit_page_numbers` are page_in_section values -- rather
        than at page 1 of a long section.

        Only for search/toc hits with a real section string. If a search hit's
        `section` is None (unsectioned Parts Seven-Ten, Annexures, or a Part's
        2-page lead-in), use read_page with its hit_pages instead -- there is no
        section string to pass here.
        """
        return ctx.deps.tools.read_section(
            section, page_from=page_from, page_to=page_to, max_pages=MAX_READ_PAGES
        )

    @agent.tool
    def read_page(
        ctx: RunContext[PurserDeps], pdf_page: int, before: int = 0, after: int = 0
    ) -> list[PageText]:
        """Read one PDF page plus optional neighbouring pages (up to 2 each side).

        Use this for unsectioned search hits (section=None) with the hit's
        hit_pages values, or whenever you want a specific page plus its
        immediate neighbours without pulling a whole section.
        """
        return ctx.deps.tools.read_page(
            pdf_page, before=before, after=after, max_pages=MAX_READ_PAGES
        )

    @agent.tool
    def lookup_term(ctx: RunContext[PurserDeps], term: str) -> GlossaryEntry | None:
        """The manual's own definition of an acronym or term of art.

        Prefer this over search for "what does X stand for" / "what is X"
        questions about an acronym or defined term -- it is a single hop and
        returns the manual's own defining wording, whereas search tends to
        surface pages that merely use the term rather than define it.
        """
        return ctx.deps.tools.lookup_term(term)

    return agent
