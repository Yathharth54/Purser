from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from purser_agent import tooling
from purser_agent.prompts import SYSTEM_PROMPT
from purser_agent.provider import require_credentials, resolve_model
from purser_agent.schemas import Answer
from purser_agent.tooling import MAX_READ_PAGES  # noqa: F401  (re-exported)
from purser_core.models import GlossaryEntry, PageText, PartName, SectionHit, TocNode
from purser_core.tools import PurserTools

# Output tokens per model call. Uncapped, a request asks for the model's
# maximum (131,072 on DeepSeek v4.1 Flash) and OpenRouter reserves credit for
# all of it up front, so a low balance rejects every question with 402. Real
# answers use 300-2,000.
MAX_OUTPUT_TOKENS = 4096


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
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS},
    )

    @agent.tool(description=tooling.SEARCH)
    def search(ctx: RunContext[PurserDeps], query: str, k: int = 8) -> list[SectionHit]:
        return ctx.deps.tools.search(query, k=k)

    @agent.tool(description=tooling.TOC)
    def toc(ctx: RunContext[PurserDeps], part: PartName | None = None) -> list[TocNode]:
        return ctx.deps.tools.toc(part=part)

    @agent.tool(description=tooling.READ_SECTION)
    def read_section(
        ctx: RunContext[PurserDeps],
        section: str,
        page_from: int = 1,
        page_to: int | None = None,
    ) -> list[PageText]:
        return ctx.deps.tools.read_section(
            section, page_from=page_from, page_to=page_to, max_pages=MAX_READ_PAGES
        )

    @agent.tool(description=tooling.READ_PAGE)
    def read_page(
        ctx: RunContext[PurserDeps], pdf_page: int, before: int = 0, after: int = 0
    ) -> list[PageText]:
        return ctx.deps.tools.read_page(
            pdf_page, before=before, after=after, max_pages=MAX_READ_PAGES
        )

    @agent.tool(description=tooling.LOOKUP_TERM)
    def lookup_term(ctx: RunContext[PurserDeps], term: str) -> GlossaryEntry | None:
        return ctx.deps.tools.lookup_term(term)

    return agent
