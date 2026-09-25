from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from purser_api import auth
from purser_api.db import engine
from purser_api.routers import chat, manual

# `src/purser_api/main.py` -> parent (purser_api) -> parent (src) -> parent (repo root).
# `Path("web/dist")` would instead resolve against the process's CWD, so the
# PWA silently never mounts unless the app happens to be started from the
# repo root -- anchoring to this file makes it independent of CWD.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DIST = _REPO_ROOT / "web" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine()  # create app.sqlite tables
    yield


app = FastAPI(
    title="Purser",
    description="Cited retrieval over the A320/321 SEP manual",
    lifespan=_lifespan,
)

# Tasks 17/18 run the PWA against this API from a Vite dev server on a
# different origin; without CORS the browser blocks every request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The passcode gate (see purser_api.auth). Added last, so it runs outermost:
# a locked request is refused before any route or other middleware sees it.
app.middleware("http")(auth.gate)

app.include_router(auth.router)
app.include_router(manual.router)
app.include_router(chat.router)

if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
