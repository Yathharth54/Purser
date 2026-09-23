from __future__ import annotations

from pathlib import Path

from purser_core.corpus import Corpus
from purser_core.embed import Embedder
from purser_core.fusion import rrf
from purser_core.glossary import expand_query, find_term
from purser_core.lexical import lexical_search
from purser_core.models import GlossaryEntry, Page, PageText, PartName, SectionHit, TocNode
from purser_core.reading import clamp_by_page_in_section
from purser_core.semantic import semantic_search

_SNIPPET_CHARS = 320
_LANE_DEPTH = 20

# search() walks the fused page ranking, grouping pages into sections, until it
# has k sections or has scanned every page `fused` holds, whichever comes
# first. `fused` holds at most 2 * _LANE_DEPTH pages (rrf's two lanes, each
# capped at _LANE_DEPTH), so this bound is really "scan everything fused
# gave us" — it does not independently limit anything on its own today, but
# is derived so it stays meaningful if _LANE_DEPTH changes. Measured median
# pages-to-reach-8-sections is 18 — see design doc §8.4.
_PAGE_SCAN_CAP = 2 * _LANE_DEPTH

# One huge section (§3.5 is 104 pages) must not bloat a single row's payload.
_MAX_HIT_PAGES = 5


def _snippet(page: Page) -> str:
    body = " ".join(ln.strip() for ln in page.lines if ln.strip())
    return body[:_SNIPPET_CHARS]


class _SectionAccum:
    """Accumulates the pages seen for one (part, section) key during the walk.

    `score` and `snippet` are fixed from the first page assigned to this
    section, which — because the walk consumes `fused` in descending-score
    order — is necessarily that section's best-scoring page.
    """

    def __init__(self, page: Page, score: float) -> None:
        self.part = page.part
        self.section = page.section
        self.section_title = page.section_title
        self.score = score
        self.hit_pages: list[int] = [page.pdf_page]
        self.hit_page_numbers: list[int] = [page.page_in_section]
        self.snippet = _snippet(page)

    def add(self, page: Page) -> None:
        if len(self.hit_pages) < _MAX_HIT_PAGES:
            self.hit_pages.append(page.pdf_page)
            self.hit_page_numbers.append(page.page_in_section)

    def to_hit(self) -> SectionHit:
        return SectionHit(
            part=self.part,
            section=self.section,
            section_title=self.section_title,
            score=self.score,
            hit_pages=self.hit_pages,
            hit_page_numbers=self.hit_page_numbers,
            snippet=self.snippet,
        )


def _to_page_text(page: Page) -> PageText:
    return PageText(
        pdf_page=page.pdf_page,
        part=page.part,
        section=page.section,
        section_title=page.section_title,
        page_in_section=page.page_in_section,
        section_total=page.section_total,
        # Furniture is dropped; the index is NOT renumbered. The model cites the
        # number it is shown, and that number must still address Page.lines.
        numbered_lines=[f"{i}|{text}" for i, text in page.content_lines()],
    )


class PurserTools:
    """The five functions the agent may call. This is the whole L2 surface."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.corpus = Corpus(data_dir)
        self.embedder = Embedder()

    def search(self, query: str, k: int = 8) -> list[SectionHit]:
        """Find which sections of the manual a topic lives in.

        `search` narrows; it does not choose. It returns one row per section —
        best-first, each carrying the pages within it that matched and a
        snippet from the best of them — for the agent to pick from with
        `read_section`/`read_page`. `k` is the number of SECTIONS returned,
        not pages. See design doc §8.4 for the recall measurement behind this.
        """
        expanded = expand_query(self.corpus, query)
        fused = rrf(
            lexical_search(self.corpus, expanded, k=_LANE_DEPTH),
            semantic_search(self.corpus, self.embedder, expanded, k=_LANE_DEPTH),
        )

        sections: dict[tuple[PartName, str | None], _SectionAccum] = {}
        for pdf_page, score in fused[:_PAGE_SCAN_CAP]:
            page = self.corpus.page(pdf_page)
            key = (page.part, page.section)
            accum = sections.get(key)
            if accum is None:
                sections[key] = _SectionAccum(page, score)
            else:
                accum.add(page)
            if len(sections) >= k:
                break

        ranked = sorted(sections.values(), key=lambda s: -s.score)
        return [accum.to_hit() for accum in ranked[:k]]

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
        self,
        section: str,
        page_from: int = 1,
        page_to: int | None = None,
        max_pages: int | None = None,
    ) -> list[PageText]:
        """Read verbatim pages of a section, in order. Out-of-range values are clamped.

        See `clamp_by_page_in_section` for the clamp invariant this relies on --
        it is shared with `GET /api/section/{section}` so the two never drift apart.
        `max_pages` keeps only the first N pages of the clamped range.
        """
        pages = self.corpus.pages_in_section(section)
        window = clamp_by_page_in_section(pages, page_from, page_to)
        if max_pages is not None:
            window = window[:max_pages]
        return [_to_page_text(p) for p in window]

    def read_page(
        self, pdf_page: int, before: int = 0, after: int = 0, max_pages: int | None = None
    ) -> list[PageText]:
        """Read one page plus optional neighbours, for cheap context expansion.

        `max_pages` bounds the whole window, split evenly either side of the page.
        """
        if max_pages is not None:
            side = max(0, (max_pages - 1) // 2)
            before, after = min(before, side), min(after, side)
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
