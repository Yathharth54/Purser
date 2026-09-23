from __future__ import annotations

import logging

from purser_agent.schemas import CiteRef
from purser_api.schemas import Citation
from purser_core.blocks import parse_blocks, table_state_after, wrap_width
from purser_core.corpus import Corpus
from purser_core.outline import annotate_depth
from purser_core.reading import page_start

log = logging.getLogger(__name__)


def resolve(corpus: Corpus, ref: CiteRef) -> Citation | None:
    """Turn a model-emitted coordinate into verbatim manual text.

    This is the only function in the codebase that produces quote text.
    `ref.line_to` is EXCLUSIVE -- the splice is `page.lines[line_from:line_to]`,
    never `line_to + 1`.
    """
    try:
        page = corpus.page(ref.pdf_page)
    except KeyError:
        log.warning("citation dropped: no page %s", ref.pdf_page)
        return None

    lo = max(0, ref.line_from)
    hi = min(len(page.lines), ref.line_to)
    if lo >= hi:
        log.warning("citation dropped: empty range %s:%s on p%s", lo, hi, ref.pdf_page)
        return None

    chrome = set(page.chrome)
    while lo < hi and (lo in chrome or not page.lines[lo].strip()):
        lo += 1
    while hi > lo and (hi - 1 in chrome or not page.lines[hi - 1].strip()):
        hi -= 1
    if lo >= hi:
        log.warning("citation dropped: pure furniture %s:%s on p%s", lo, hi, ref.pdf_page)
        return None

    # `parse_blocks` treats its `chrome` argument as indices INTO the `lines`
    # list it is handed. We are handing it a SLICE (`page.lines[lo:hi]`), so
    # `page.chrome` -- which is page-absolute -- must be rebased onto that
    # slice's own indexing, or interior furniture is mis-skipped (or, worse,
    # real procedure text is skipped once lo > 0). `blocks` is only how
    # `text` is drawn; `text` itself stays the untouched, byte-exact splice.
    #
    # `blocks` must also match what the section reader draws for the same
    # lines, so the slice is parsed with the state it actually opens in: any
    # table carried from earlier pages or begun above `lo` on this page, the
    # headings open at `lo`, and the PAGE's wrap width rather than one
    # recomputed from the few lines in the slice.
    start = page_start(corpus, page)
    full = wrap_width(page.lines, page.chrome)
    above, above_chrome = page.lines[:lo], [c for c in page.chrome if c < lo]
    in_table, edge = table_state_after(
        above, above_chrome, start_in_table=start.in_table, full=full
    )
    open_headings = annotate_depth(
        parse_blocks(above, above_chrome, start_in_table=start.in_table, full=full),
        list(start.stack),
    )
    blocks = parse_blocks(
        page.lines[lo:hi],
        [c - lo for c in page.chrome if lo <= c < hi],
        start_in_table=in_table,
        table_indent=edge,
        full=full,
    )
    # Nest headings inside the quote, but never indent the whole quote under
    # the section it sits in: that section is named in `context` instead.
    # Shift so the shallowest block sits at 0 -- relative nesting survives
    # (a heading in the quote still owns what follows it).
    annotate_depth(blocks, open_headings)
    base = min(b.depth for b in blocks) if blocks else 0
    for block in blocks:
        block.depth -= base

    return Citation(
        pdf_page=page.pdf_page,
        part=page.part,
        section=page.section,
        section_title=page.section_title,
        page_in_section=page.page_in_section,
        revision=page.revision,
        effective=page.effective,
        text="\n".join(page.lines[lo:hi]),
        blocks=blocks,
        context=_context(open_headings, blocks),
    )


def _context(open_headings: list[tuple[int, str]], blocks: list) -> str | None:
    """The section the quote sits in. When the quote opens with a heading, that
    heading closes every open section of its rank or deeper -- naming one of
    those would label the card with a sibling the quote is not part of."""
    if blocks and blocks[0].kind == "heading":
        open_headings = [h for h in open_headings if h[0] < blocks[0].level]
    return open_headings[-1][1] if open_headings else None


def resolve_all(corpus: Corpus, refs: list[CiteRef]) -> list[Citation]:
    """A malformed ref costs one citation, never the whole answer."""
    return [c for c in (resolve(corpus, r) for r in refs) if c is not None]
