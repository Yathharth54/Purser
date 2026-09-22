from __future__ import annotations

import re

_HEADER = re.compile(r"^\s*(?P<title>.*?)\s+(?P<rev>Issue\s+[IVX]+\s+Revision\s+\d+)\s*$", re.I | re.M)


def parse_header(page_text: str) -> tuple[str | None, str | None]:
    """Extract (section_title, revision) from the page header block.

    The header line reads '<Section Title>    Issue IX    Revision 00'.
    """
    m = _HEADER.search(page_text)
    if not m:
        return None, None
    title = m.group("title").strip() or None
    revision = " ".join(m.group("rev").split())
    return title, revision
