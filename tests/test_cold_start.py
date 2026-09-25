"""A cold start should only pay for what the first request needs.

On Vercel the first request after idle waits for the whole app to import and
start. The passcode check (the app's first call) needs neither the AI agent
library nor the database, so neither may load at import or startup.
"""

from __future__ import annotations

import subprocess
import sys

from fastapi.testclient import TestClient


def test_importing_the_app_does_not_load_the_agent_library():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import purser_api.main; print('pydantic_ai' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": "src"},
    )
    assert out.stdout.strip() == "False"


def test_the_session_check_does_not_connect_to_the_database(tmp_path, monkeypatch):
    import purser_api.db as db

    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    db.reset_engine()
    from purser_api.main import app

    with TestClient(app) as c:
        assert c.get("/api/session").status_code == 200
        assert db._engine is None
    db.reset_engine()
