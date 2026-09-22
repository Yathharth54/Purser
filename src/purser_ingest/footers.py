from __future__ import annotations

import re
from datetime import date, datetime

from purser_core.models import PageCoord, PartName

_EFF = r"Effective\s*(?P<eff>\d{1,2}\s+\w+\s+\d{4})"
_PG = r"Page\s+(?P<p>\d+)\s+of\s+(?P<t>\d+)"

SEC = re.compile(rf"(?P<part>PART\s+[A-Z]+)\s+Section\s+(?P<section>[\d.]+)\s+{_PG}\s+{_EFF}", re.I)
PART = re.compile(rf"(?P<part>PART\s+[A-Z]+)\s+{_PG}\s+{_EFF}", re.I)
ANNEX = re.compile(rf"(?P<part>Annexures?)\s+{_PG}\s+{_EFF}", re.I)
FRONT = re.compile(
    rf"^\s*(?P<code>GOTC|GTOC|ROR|DL|LEP|HIS|LOC|FDW|ACK|ISP)\s+"
    rf"(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+{_EFF}",
    re.I | re.M,
)

# Order matters: SEC before PART, or "PART SIX Section 6.7" matches PART with section lost.
_PATTERNS = (SEC, PART, ANNEX, FRONT)


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%d %B %Y").date()


def parse_footer(page_text: str) -> PageCoord | None:
    """Parse the last footer on a page. Returns None when the page carries none."""
    for pattern in _PATTERNS:
        matches = list(pattern.finditer(page_text))
        if not matches:
            continue
        m = matches[-1]  # last occurrence wins
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
