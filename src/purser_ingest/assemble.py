from __future__ import annotations

from datetime import date

from purser_core.models import Page, PartName
from purser_ingest.footers import parse_footer
from purser_ingest.headers import parse_header

_FRONT_FALLBACK_PAGES = 4  # cover, two blanks, the DGCA approval letter — no footers


def _clean_lines(raw: str) -> list[str]:
    return [ln.rstrip() for ln in raw.split("\n")]


def _last_nonempty_line(raw: str) -> str:
    for line in reversed(raw.split("\n")):
        if line.strip():
            return line.strip()
    return ""


def _parse_footer_or_raise(raw: str, idx: int):
    """Wrap parse_footer so any failure names the page and the offending footer text.

    assemble() is the only layer that knows the page number, so it is the right place
    to attach that context before letting the failure propagate.
    """
    try:
        return parse_footer(raw)
    except Exception as exc:
        footer_text = _last_nonempty_line(raw)
        raise ValueError(
            f"page {idx}: failed to parse footer ({exc}); footer text: {footer_text!r}"
        ) from exc


def assemble(raw_pages: list[str]) -> list[Page]:
    """Turn raw page strings into Page records with full tree coordinates."""
    pages: list[Page] = []
    titles: dict[tuple[PartName, str | None], str] = {}

    for idx, raw in enumerate(raw_pages, start=1):
        coord = _parse_footer_or_raise(raw, idx)
        title, revision = parse_header(raw)

        if coord is None:
            if idx > _FRONT_FALLBACK_PAGES:
                raise ValueError(f"page {idx} has no parseable footer")
            pages.append(
                Page(
                    pdf_page=idx,
                    part=PartName.FRONT,
                    section=None,
                    section_title="Manual Administration",
                    page_in_section=idx,
                    section_total=_FRONT_FALLBACK_PAGES,
                    effective=date(2023, 5, 18),
                    revision=revision,
                    lines=_clean_lines(raw),
                    text=raw,
                )
            )
            continue

        key = (coord.part, coord.section)
        if title and key not in titles:
            titles[key] = title

        pages.append(
            Page(
                pdf_page=idx,
                part=coord.part,
                section=coord.section,
                section_title=titles.get(key) or title,
                page_in_section=coord.page_in_section,
                section_total=coord.section_total,
                effective=coord.effective,
                revision=revision,
                lines=_clean_lines(raw),
                text=raw,
            )
        )

    # Backfill titles onto pages seen before their section's title line appeared.
    for p in pages:
        if p.section_title is None:
            p.section_title = titles.get((p.part, p.section))
    return pages
