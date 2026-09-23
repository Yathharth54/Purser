"""Vercel entrypoint. Vercel looks for a top-level `app` in ./app.py.

The code lives in a src/ layout; putting src/ on the path here keeps the import
independent of whether (and how) the platform installs this project as a package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from purser_api.main import app  # noqa: E402

__all__ = ["app"]
