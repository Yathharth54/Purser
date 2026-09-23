"""Which heading owns which block: the manual as nested sections.

`parse_blocks` returns a flat list, and a flat list renders as a stream of
fragments. Here each block gets a `depth` -- how many open headings enclose
it -- so a renderer can draw a section as one unit. The open headings are
returned as a stack so a caller walking a section page by page can hand them
to the next page: a heading on page 5 still owns the top of page 6.
"""

from __future__ import annotations

from purser_core.models import Block

# (heading level, heading text), outermost first.
HeadingStack = list[tuple[int, str]]


def annotate_depth(blocks: list[Block], stack: HeadingStack) -> HeadingStack:
    """Set `depth` on each block in place; return the headings still open after them.

    A heading of level L closes every open heading of level >= L, then opens
    its own. A skipped level ("1." then "1.1.1") nests one step, not two:
    depth counts enclosing headings, not numbering depth. Subheadings are
    minor labels inside the current section and open nothing. `stack` is not
    mutated.
    """
    open_: HeadingStack = list(stack)
    for block in blocks:
        if block.kind == "heading":
            while open_ and open_[-1][0] >= block.level:
                open_.pop()
            block.depth = len(open_)
            open_.append((block.level, block.text))
        else:
            block.depth = len(open_)
    return open_
