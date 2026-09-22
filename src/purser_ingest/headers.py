from __future__ import annotations

import re

# Matches a single physical line that ends with the revision token, optionally
# preceded by title text on that SAME line.
_REV_LINE = re.compile(r"^(?P<pre>.*?)(?P<rev>Issue\s+[IVX]+\s+Revision\s+\d+)\s*$", re.IGNORECASE)


def parse_header(page_text: str) -> tuple[str | None, str | None]:
    """Extract (section_title, revision) from the page header block.

    Normally the header is one physical line: '<Section Title>  Issue IX  Revision
    00'. But `pdftotext -layout` wraps a long title across THREE physical lines,
    printing the revision token alone on its own line, with the wrapped remainder
    on the line AFTER it:

        'Rapid and slow decompression (Pressurization'
        '                       Issue IX   Revision 00'
        'Problems)'                                      <- belongs to the title

    Detected by the revision line itself carrying no title text before it on that
    same line ("pre" is empty); the title is then reassembled from the line above
    (its start) and the line below (its wrapped remainder).
    """
    lines = page_text.split("\n")
    for i, line in enumerate(lines):
        m = _REV_LINE.match(line)
        if not m:
            continue
        revision = " ".join(m.group("rev").split())
        pre = m.group("pre").strip()
        if pre:
            title = pre
        else:
            before = lines[i - 1].strip() if i > 0 else ""
            after = lines[i + 1].strip() if i + 1 < len(lines) else ""
            title = " ".join(part for part in (before, after) if part)
        return (title or None), revision
    return None, None
