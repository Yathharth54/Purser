"""Load .env before tests run, so live tests see OPENAI_API_KEY.

Nothing else in the app reads .env -- production sets real environment
variables. A missing .env (e.g. in CI) is not an error; dotenv just no-ops.
Never print or log the key itself.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=False)
