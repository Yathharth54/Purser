from __future__ import annotations

import re
from datetime import date, datetime

from purser_core.models import PageCoord, PartName

# The footer always lives in the last few non-blank lines of the page. Restricting
# the search to this window (rather than scanning the whole page body) is what
# makes `matches[-1]` below meaningful: without it, any line elsewhere on the page
# that happens to match a footer pattern -- a cross-reference, a footnote -- would
# be positionally last without being the actual footer.
_FOOTER_WINDOW = 5

_EFF = r"Effective\s*(?P<eff>\d{1,2}\s+\w+\s+\d{4})\s*$"
_PG = r"Page\s+(?P<p>\d+)\s+of\s+(?P<t>\d+)"

SEC = re.compile(
    rf"(?P<part>PART\s+[A-Z]+)\s+Section\s+(?P<section>[\d.]+)\s+{_PG}\s+{_EFF}",
    re.IGNORECASE | re.MULTILINE,
)
PART = re.compile(rf"(?P<part>PART\s+[A-Z]+)\s+{_PG}\s+{_EFF}", re.IGNORECASE | re.MULTILINE)
ANNEX = re.compile(rf"(?P<part>Annexures?)\s+{_PG}\s+{_EFF}", re.IGNORECASE | re.MULTILINE)
FRONT = re.compile(
    rf"^\s*(?P<code>GOTC|GTOC|ROR|DL|LEP|HIS|LOC|FDW|ACK|ISP)\s+"
    rf"(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+{_EFF}",
    re.IGNORECASE | re.MULTILINE,
)

# Order matters defensively, not because of an actual ambiguity: PART requires
# "Page" immediately after the part name, so it cannot match a SEC-shaped footer
# ("PART SIX Section 6.7 ...") in the first place -- 0 of 1,226 pages match more
# than one pattern class. Trying SEC first costs nothing and protects against a
# future footer variant where that stops being true.
_PATTERNS = (SEC, PART, ANNEX, FRONT)


def _parse_date(raw: str) -> date:
    # strptime is the only stdlib parser for a "%d %B %Y" month-name date; the
    # manual's footer carries no time or timezone component, so there is nothing
    # to be naive about once .date() discards the (unused) time part.
    return datetime.strptime(raw.strip(), "%d %B %Y").date()  # noqa: DTZ007


def _footer_region(page_text: str) -> str:
    """The last few non-blank lines of the page, where the footer always lives."""
    lines = [ln for ln in page_text.split("\n") if ln.strip()]
    return "\n".join(lines[-_FOOTER_WINDOW:])


def parse_footer(page_text: str) -> PageCoord | None:
    """Parse the last footer on a page. Returns None when the page carries none."""
    region = _footer_region(page_text)
    for pattern in _PATTERNS:
        matches = list(pattern.finditer(region))
        if not matches:
            continue
        m = matches[-1]  # last occurrence within the footer region wins
        g = m.groupdict()
        if "code" in g:
            part, section = PartName.FRONT, None
        elif g.get("part", "").lower().startswith("annexure"):
            part, section = PartName.ANNEX, None
        else:
            part = PartName(" ".join(g["part"].upper().split()))
            section = g.get("section")
        return PageCoord(
            part=part,
            section=section,
            page_in_section=int(g["p"]),
            section_total=int(g["t"]),
            effective=_parse_date(g["eff"]),
        )
    return None
