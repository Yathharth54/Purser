from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from purser_api.deps import get_pdf_path, get_tools
from purser_core.models import PageText, TocNode
from purser_ingest.render import render_page

router = APIRouter(prefix="/api", tags=["manual"])

_LAST_PDF_PAGE = 1226


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/toc", response_model=list[TocNode])
def toc() -> list[TocNode]:
    return get_tools().toc()


@router.get("/section/{section}", response_model=list[PageText])
def section(section: str, page_from: int = 1, page_to: int | None = None) -> list[PageText]:
    pages = get_tools().read_section(section, page_from=page_from, page_to=page_to)
    if not pages:
        raise HTTPException(status_code=404, detail=f"no such section: {section}")
    return pages


@router.get("/page/{pdf_page}/image")
def page_image(pdf_page: int) -> FileResponse:
    if not 1 <= pdf_page <= _LAST_PDF_PAGE:
        raise HTTPException(status_code=404, detail="page out of range")
    path = render_page(get_pdf_path(), pdf_page)
    return FileResponse(path, media_type="image/webp")
