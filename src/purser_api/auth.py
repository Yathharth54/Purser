"""The passcode gate.

One shared passcode (PURSER_PASSCODE) for a single tester. When it is set,
every /api route except the few in OPEN answers 401 without a valid session
cookie -- the manual, her chats and the page images included. When it is not
set (local development, tests) the app is open, as before.

The cookie never carries the passcode: it holds an HMAC keyed by it, so
nothing readable leaks, and changing the passcode invalidates every device.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlmodel import select

from purser_api.db import LoginFailure, session

COOKIE = "purser_session"
OPEN = {"/api/health", "/api/session", "/api/login"}
# Not under /api, but they map every endpoint and name the manual.
_DOCS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
WRONG_PASSCODE_DELAY = 1.0  # seconds; slows guessing (tests set it to 0)
# Parallel requests defeat a per-request delay, so wrong guesses are also
# counted in the database -- shared by every instance -- and past this many in
# FAILURE_WINDOW, all logins pause until the window clears.
MAX_FAILURES = 10
FAILURE_WINDOW = timedelta(minutes=15)
_ONE_YEAR = 365 * 24 * 3600

router = APIRouter(prefix="/api", tags=["auth"])


def _passcode() -> str:
    return os.environ.get("PURSER_PASSCODE", "")


def _token(passcode: str) -> str:
    return hmac.new(passcode.encode(), b"purser-session-v1", hashlib.sha256).hexdigest()


def is_authenticated(request: Request) -> bool:
    passcode = _passcode()
    if not passcode:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(passcode))


def _route_path(request: Request) -> str:
    """The path Starlette routes on: scope["path"] with any root_path removed.

    Checking the raw path would let `/prefix/api/toc` slip past the gate
    whenever the app is mounted under a prefix, yet still reach the route.
    """
    path, root = request.scope["path"], request.scope.get("root_path", "")
    return path[len(root) :] or "/" if root and path.startswith(root) else path


async def gate(request: Request, call_next):
    """HTTP middleware: close every non-open /api route (and the API docs)
    without a session."""
    path = _route_path(request)
    closed = (path.startswith("/api/") and path not in OPEN) or path in _DOCS
    if closed and not is_authenticated(request):
        return JSONResponse({"detail": "passcode required"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    passcode: str


@router.get("/session")
def session_state(request: Request) -> dict:
    return {"authenticated": is_authenticated(request), "required": bool(_passcode())}


@router.post("/login")
async def login(body: Login, request: Request, response: Response):
    passcode = _passcode()
    if not passcode:
        return {"ok": True}
    since = datetime.now(UTC) - FAILURE_WINDOW
    with session() as s:
        recent = s.exec(select(func.count()).where(LoginFailure.at >= since)).one()
        if recent >= MAX_FAILURES:
            return JSONResponse(
                {"detail": "too many wrong passcodes; try again in 15 minutes"}, status_code=429
            )
        if not hmac.compare_digest(body.passcode.encode(), passcode.encode()):
            s.add(LoginFailure())
            # Keep the table tiny: anything older than a day is irrelevant.
            s.exec(delete(LoginFailure).where(LoginFailure.at < since - timedelta(days=1)))
            s.commit()
            await asyncio.sleep(WRONG_PASSCODE_DELAY)
            return JSONResponse({"detail": "wrong passcode"}, status_code=401)
    response.set_cookie(
        COOKIE,
        _token(passcode),
        max_age=_ONE_YEAR,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return {"ok": True}
