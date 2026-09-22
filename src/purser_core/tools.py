from __future__ import annotations

from pathlib import Path

from purser_core.corpus import Corpus
from purser_core.embed import Embedder
from purser_core.fusion import rrf
from purser_core.glossary import expand_query, find_term
from purser_core.lexical import lexical_search
from purser_core.models import GlossaryEntry, Page, PageText, PartName, SearchHit, TocNode
from purser_core.semantic import semantic_search

_SNIPPET_CHARS = 320
_LANE_DEPTH = 20


def _snippet(page: Page) -> str:
    body = " ".join(ln.strip() for ln in page.lines if ln.strip())
    return body[:_SNIPPET_CHARS]


def _to_page_text(page: Page) -> PageText:
    return PageText(
        pdf_page=page.pdf_page,
        part=page.part,
        section=page.section,
        section_title=page.section_title,
        page_in_section=page.page_in_section,
        numbered_lines=[f"{i}| {ln}" for i, ln in enumerate(page.lines)],
    )


class PurserTools:
    """The five functions the agent may call. This is the whole L2 surface."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.corpus = Corpus(data_dir)
        self.embedder = Embedder()

    def search(self, query: str, k: int = 8) -> list[SearchHit]:
        """Find where in the manual a topic lives. Returns coordinates and a snippet."""
        expanded = expand_query(self.corpus, query)
        fused = rrf(
            lexical_search(self.corpus, expanded, k=_LANE_DEPTH),
            semantic_search(self.corpus, self.embedder, expanded, k=_LANE_DEPTH),
        )
        hits: list[SearchHit] = []
        for pdf_page, score in fused[:k]:
            page = self.corpus.page(pdf_page)
            hits.append(
                SearchHit(
                    pdf_page=page.pdf_page,
                    part=page.part,
                    section=page.section,
                    section_title=page.section_title,
                    page_in_section=page.page_in_section,
                    snippet=_snippet(page),
                    score=score,
                )
            )
        return hits

    def toc(self, part: PartName | None = None) -> list[TocNode]:
        """The manual's Part/Section tree.

        Each Part (plus Front Matter and Annexures) opens with a 2-page
        lead-in that carries no Section footer token, so its TocNode has
        section=None. Those pages are real content — structure here is
        parsed, never inferred — so filtering by Part keeps that node: it is
        part of what "Part Four" contains, just as its numbered sections are.
        """
        nodes = self.corpus.toc
        return [n for n in nodes if n.part == part] if part is not None else nodes

    def read_section(
        self, section: str, page_from: int = 1, page_to: int | None = None
    ) -> list[PageText]:
        """Read verbatim pages of a section, in order. Out-of-range values are clamped.

        Bounds are clamped against the section's actual page_in_section range, not
        against the count of pages returned. Five sections (1.1, 2.1, 3.1, 4.1, 6.1)
        open at page_in_section 3 rather than 1 (each Part has a 2-page lead-in), so
        len(pages) undercounts the true upper bound for those sections by 2. Using
        len(pages) here would silently drop the section's last two pages whenever
        page_to is left at its default or set beyond the section's end.
        """
        pages = self.corpus.pages_in_section(section)
        if not pages:
            return []
        last = max(p.page_in_section for p in pages)
        lo = max(1, page_from)
        hi = min(last, page_to) if page_to is not None else last
        return [_to_page_text(p) for p in pages if lo <= p.page_in_section <= hi]

    def read_page(self, pdf_page: int, before: int = 0, after: int = 0) -> list[PageText]:
        """Read one page plus optional neighbours, for cheap context expansion."""
        out: list[PageText] = []
        for n in range(pdf_page - before, pdf_page + after + 1):
            try:
                out.append(_to_page_text(self.corpus.page(n)))
            except KeyError:
                continue
        return out

    def lookup_term(self, term: str) -> GlossaryEntry | None:
        """The manual's own definition of an acronym or term of art."""
        return find_term(self.corpus, term)
