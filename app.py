"""Vercel entrypoint. Vercel looks for a top-level `app` in ./app.py.

The code lives in a src/ layout; putting src/ on the path here keeps the import
independent of whether (and how) the platform installs this project as a package.
"""

import sys
import time
from pathlib import Path

_T0 = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from purser_api.main import app  # noqa: E402

# Cold-start visibility in Vercel's runtime logs.
print(f"[startup] app imported in {time.perf_counter() - _T0:.2f}s", flush=True)

__all__ = ["app"]
