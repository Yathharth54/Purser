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

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

COOKIE = "purser_session"
OPEN = {"/api/health", "/api/session", "/api/login"}
WRONG_PASSCODE_DELAY = 1.0  # seconds; slows guessing (tests set it to 0)
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


async def gate(request: Request, call_next):
    """HTTP middleware: close every non-open /api route without a session."""
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN and not is_authenticated(request):
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
    if not hmac.compare_digest(body.passcode.encode(), passcode.encode()):
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
