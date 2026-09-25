from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from purser_api import pages
from purser_api.deps import get_corpus, get_pdf_path, get_tools
from purser_core.models import ReadingPage, TocNode
from purser_core.reading import clamp_by_page_in_section, reading_pages
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

    Clamping is shared with `PurserTools.read_section` via
    `clamp_by_page_in_section` -- see its docstring for the clamp invariant
    (several sections open at page_in_section 3, not 1) so this reader and
    the agent's own view of a section can't silently drift apart on it.
    """
    pages = reading_pages(get_corpus(), section)
    if not pages:
        raise HTTPException(status_code=404, detail=f"no such section: {section}")
    return clamp_by_page_in_section(pages, page_from, page_to)


@router.get("/page/{pdf_page}/image")
def page_image(pdf_page: int) -> FileResponse:
    if not 1 <= pdf_page <= _LAST_PDF_PAGE:
        raise HTTPException(status_code=404, detail="page out of range")

    try:
        pdf_path: Path | None = get_pdf_path()
    except KeyError:
        pdf_path = None

    if pdf_path is not None and pdf_path.is_file():
        # Locally and in Docker: render from the PDF itself.
        try:
            path = render_page(pdf_path, pdf_page)
        except (OSError, RuntimeError, IndexError, ValueError) as exc:
            # An unreadable PDF (OSError), a page pypdfium2 can't load
            # (PdfiumError is a RuntimeError), or a page the PDF doesn't have:
            # the running deployment's problem, not the client's -- 503, not an
            # unhandled 500 traceback.
            detail = f"page rendering unavailable: {exc}"
            raise HTTPException(status_code=503, detail=detail) from exc
    elif pages.configured():
        # On Vercel, where the PDF is never deployed: the pre-rendered page
        # from the private Blob store (see purser_api.pages).
        try:
            path = pages.fetch_page(pdf_page)
        except pages.PageNotStored as exc:
            raise HTTPException(status_code=503, detail=f"page image not uploaded: {exc}") from exc
        except Exception as exc:  # the Blob SDK's errors, network failures
            raise HTTPException(status_code=503, detail=f"page store unavailable: {exc}") from exc
    else:
        raise HTTPException(status_code=503, detail="no manual PDF and no page store configured")

    # Behind the passcode: only her own browser may cache it (a week), never a
    # shared CDN, which would hand the image out without checking the cookie.
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "private, max-age=604800"}
    )
