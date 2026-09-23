"""Which lines on a page are furniture rather than content.

IMPORTANT: this module returns INDICES. Nothing downstream may renumber
Page.lines. CiteRef.line_from/line_to are indices into the full list, and every
citation in var/app.sqlite would silently point somewhere else if they moved --
while still splicing text that reads like plausible manual prose.
"""

from __future__ import annotations

import re

# Derived by counting hits across the whole corpus, not guessed:
#   InterGlobe/ifly.SEP  1,229   NOT A CONTROLLED COPY  1,226
#   manual title         1,223   Issue N Revision NN    1,200
#   Page N of M          1,200   Effective <date>          22
_CHROME = re.compile(
    r"InterGlobe Aviation Limited"
    r"|ifly\.SEP"
    r"|NOT A CONTROLLED COPY"
    r"|SAFETY AND EMERGENCY PROCEDURES MANUAL"
    r"|Issue\s+[IVXLC]+\s+Revision\s+\d+"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|Effective\s*\d{1,2}\s"
)


def chrome_line_indices(lines: list[str]) -> list[int]:
    """Indices of page-furniture lines. Blank lines are NOT chrome."""
    return [i for i, line in enumerate(lines) if line.strip() and _CHROME.search(line)]
