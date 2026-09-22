from __future__ import annotations

from datetime import date

from purser_core.models import Page, PartName
from purser_ingest.footers import parse_footer
from purser_ingest.headers import parse_header

_FRONT_FALLBACK_PAGES = 4  # cover, two blanks, the DGCA approval letter — no footers
_FRONT_MATTER_TITLE = "Manual Administration"


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
    """Turn raw page strings into Page records with full tree coordinates.

    `raw_pages` must already be in physical page order -- pdf_page is assigned
    from list position, so this is the one place that order matters. Every
    cross-page resolution below (title backfill, the Front Matter effective
    date) runs over `pages` explicitly sorted by `pdf_page` rather than assumed,
    the same discipline `toc_build.build_toc` applies for the same reason.
    """
    pages: list[Page] = []
    titles: dict[tuple[PartName, str | None], str] = {}

    for idx, raw in enumerate(raw_pages, start=1):
        coord = _parse_footer_or_raise(raw, idx)
        title, revision = parse_header(raw)
        lines = _clean_lines(raw)

        if coord is None:
            if idx > _FRONT_FALLBACK_PAGES:
                raise ValueError(f"page {idx} has no parseable footer")
            pages.append(
                Page(
                    pdf_page=idx,
                    part=PartName.FRONT,
                    section=None,
                    section_title=_FRONT_MATTER_TITLE,
                    page_in_section=idx,
                    section_total=_FRONT_FALLBACK_PAGES,
                    effective=date.min,  # backfilled below, once a real date is known
                    revision=revision,
                    lines=lines,
                    text="\n".join(lines),
                )
            )
            continue

        key = (coord.part, coord.section)
        if title and key not in titles and coord.part is not PartName.FRONT:
            titles[key] = title

        pages.append(
            Page(
                pdf_page=idx,
                part=coord.part,
                section=coord.section,
                section_title=(
                    _FRONT_MATTER_TITLE
                    if coord.part is PartName.FRONT
                    else titles.get(key) or title
                ),
                page_in_section=coord.page_in_section,
                section_total=coord.section_total,
                effective=coord.effective,
                revision=revision,
                lines=lines,
                text="\n".join(lines),
            )
        )

    pages.sort(key=lambda p: p.pdf_page)

    # Backfill titles onto pages seen before their section's title line appeared.
    # Front Matter (pages 1-26: the 4 footerless pages plus the footer-bearing
    # ones that follow) gets one consistent title rather than a title on some
    # pages and None on others within the same block.
    for p in pages:
        if p.part is PartName.FRONT:
            p.section_title = _FRONT_MATTER_TITLE
        elif p.section_title is None:
            p.section_title = titles.get((p.part, p.section))

    # Front-matter pages (1..4) carry no footer, so they have no effective date
    # of their own. Derive one from the first page that DOES parse a footer,
    # rather than hardcoding a value that silently goes stale on the next
    # revision (principle 3: structure is parsed, never inferred).
    first_effective = next((p.effective for p in pages if p.pdf_page > _FRONT_FALLBACK_PAGES), None)
    if first_effective is not None:
        for p in pages:
            if p.pdf_page <= _FRONT_FALLBACK_PAGES:
                p.effective = first_effective

    return pages
