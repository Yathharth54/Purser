"""Load .env before tests run, so live tests see OPENAI_API_KEY.

Nothing else in the app reads .env -- production sets real environment
variables. A missing .env (e.g. in CI) is not an error; dotenv just no-ops.
Never print or log the key itself.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=False)

# .env also carries production settings. Tests must never write to the live
# Neon database or be locked out by the app passcode, so drop them here:
# chats go to a throwaway SQLite file and auth is off unless a test opts in.
for _var in ("DATABASE_URL", "DATABASE_URL_UNPOOLED", "PGHOST", "PURSER_PASSCODE"):
    os.environ.pop(_var, None)
