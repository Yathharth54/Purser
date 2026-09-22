from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from purser_api.db import engine
from purser_api.routers import chat, manual

app = FastAPI(title="Purser", description="Cited retrieval over the A320/321 SEP manual")
app.include_router(manual.router)
app.include_router(chat.router)


@app.on_event("startup")
def _startup() -> None:
    engine()  # create app.sqlite tables


_DIST = Path("web/dist")
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
