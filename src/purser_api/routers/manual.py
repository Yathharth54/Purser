from __future__ import annotations

import subprocess

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from purser_api.deps import get_corpus, get_pdf_path, get_tools
from purser_core.models import ReadingPage, TocNode
from purser_core.reading import reading_pages
from purser_ingest.render import render_page

router = APIRouter(prefix="/api", tags=["manual"])

_LAST_PDF_PAGE = 1226


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/toc", response_model=list[TocNode])
def toc() -> list[TocNode]:
    return get_tools().toc()


@router.get("/section/{section}", response_model=list[ReadingPage])
def section(
    section: str,
    page_from: int = Query(1, ge=1),
    page_to: int | None = Query(None, ge=1),
) -> list[ReadingPage]:
    """The section as a person reads it -- whole pages, parsed into blocks.

    Bounds are clamped against the section's actual `page_in_section` range,
    same as `PurserTools.read_section` (see its docstring): several sections
    open at page_in_section 3, so clamping against the returned list's length
    would silently drop the section's last two pages.
    """
    pages = reading_pages(get_corpus(), section)
    if not pages:
        raise HTTPException(status_code=404, detail=f"no such section: {section}")
    last = max(p.page_in_section for p in pages)
    lo = max(1, page_from)
    hi = min(last, page_to) if page_to is not None else last
    return [p for p in pages if lo <= p.page_in_section <= hi]


@router.get("/page/{pdf_page}/image")
def page_image(pdf_page: int) -> FileResponse:
    if not 1 <= pdf_page <= _LAST_PDF_PAGE:
        raise HTTPException(status_code=404, detail="page out of range")

    try:
        pdf_path = get_pdf_path()
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="PURSER_PDF_PATH is not configured") from exc

    try:
        path = render_page(pdf_path, pdf_page)
    except (OSError, subprocess.CalledProcessError) as exc:
        # A missing pdftoppm binary (OSError/FileNotFoundError) or a missing/bad
        # PDF at PURSER_PDF_PATH (pdftoppm exits nonzero -> CalledProcessError)
        # are both misconfiguration of the running container, not a client
        # error and not a server bug -- 503, not an unhandled 500 traceback.
        raise HTTPException(status_code=503, detail=f"page rendering unavailable: {exc}") from exc

    return FileResponse(path, media_type="image/webp")
