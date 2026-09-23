"""Which lines on a page are furniture rather than content.

IMPORTANT: this module returns INDICES. Nothing downstream may renumber
Page.lines. CiteRef.line_from/line_to are indices into the full list, and every
citation in var/app.sqlite would silently point somewhere else if they moved --
while still splicing text that reads like plausible manual prose.
"""

from __future__ import annotations

import re

# Derived by counting matches across the whole corpus:
# Pattern                                  Total hits  Unique to this pattern
#   InterGlobe Aviation Limited                1,217    0 (overlaps with ifly.SEP)
#   ifly.SEP                                   1,228    11
#   NOT A CONTROLLED COPY                      1,226    0 (always with other patterns)
#   SAFETY AND EMERGENCY PROCEDURES MANUAL     1,223    0 (always with other patterns)
#   Issue\s+[IVXLC]+\s+Revision\s+\d+          1,200    0 (always with other patterns)
#   Page\s+\d+\s+of\s+\d+                      1,200    0 (currently subsumed by Effective)
#   Effective\s*\d{1,2}\s                      1,222    22 (the only pattern catching these)
#
# Note: Page N of M has no unique hits currently—every instance also matches Effective.
# It is retained deliberately as insurance against future footer format revisions.
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
