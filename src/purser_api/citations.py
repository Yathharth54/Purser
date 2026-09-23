from __future__ import annotations

import logging

from purser_agent.schemas import CiteRef
from purser_api.schemas import Citation
from purser_core.blocks import parse_blocks
from purser_core.corpus import Corpus

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
    blocks = parse_blocks(page.lines[lo:hi], [c - lo for c in page.chrome if lo <= c < hi])

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
    )


def resolve_all(corpus: Corpus, refs: list[CiteRef]) -> list[Citation]:
    """A malformed ref costs one citation, never the whole answer."""
    return [c for c in (resolve(corpus, r) for r in refs) if c is not None]
