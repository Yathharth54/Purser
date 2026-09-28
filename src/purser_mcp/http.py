"""/mcp: the MCP server over stateless Streamable HTTP, behind a bearer token.

Off unless PURSER_MCP_TOKEN is set (404). Closed without `Authorization:
Bearer <token>` (401). POST only: in stateless mode a GET opens a stream that
never ends, which on Vercel is a function held for its full 300 s (405).

The SDK is imported, and its app built, on the first authorised request, so a
PWA cold start never pays for it. The SDK's session manager must be running
(`session_manager.run()`), and a sub-app's lifespan never runs under FastAPI,
so it runs in a background task for the life of the event loop -- and is
rebuilt if the loop changes, since its task group belongs to the old one.
"""

from __future__ import annotations

import asyncio
import hmac
import os

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN_VAR = "PURSER_MCP_TOKEN"


def _token() -> str:
    # Stripped: `echo tok | vercel env add` stores the trailing newline.
    return os.environ.get(TOKEN_VAR, "").strip()


def _presented(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            scheme, _, credential = value.decode("latin-1").partition(" ")
            return credential.strip() if scheme.lower() == "bearer" else ""
    return ""


class McpEndpoint:
    def __init__(self) -> None:
        self._app: ASGIApp | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        self._task: asyncio.Task | None = None  # held so the loop does not drop it

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _token()
        if not token:
            return await Response(status_code=404)(scope, receive, send)
        if not hmac.compare_digest(_presented(scope).encode(), token.encode()):
            return await Response(
                status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )(scope, receive, send)
        if scope["method"] != "POST":
            return await Response(status_code=405, headers={"Allow": "POST"})(
                scope, receive, send
            )
        app = await self._ready()
        await app(scope, receive, send)

    async def _ready(self) -> ASGIApp:
        loop = asyncio.get_running_loop()
        if self._app is not None and self._loop is loop:
            return self._app
        if self._lock is None or self._loop is not loop:
            self._lock, self._loop, self._app = asyncio.Lock(), loop, None
        async with self._lock:
            if self._app is None:
                self._app = await self._start()
        return self._app

    async def _start(self) -> ASGIApp:
        from mcp.server.transport_security import TransportSecuritySettings

        from purser_mcp.server import build_server

        server = build_server()
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            # The SDK's default (host 127.0.0.1) rejects any real Host header.
            # The bearer token above is the gate.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        ready = asyncio.Event()

        async def hold() -> None:
            async with server.session_manager.run():
                ready.set()
                await asyncio.Event().wait()

        self._task = asyncio.create_task(hold())
        await ready.wait()
        return app
