# syntax=docker/dockerfile:1

# --- web build ---------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime -----------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

# poppler-utils gives us pdftotext, used by ingest (`purser ingest`). Page
# images no longer need it -- they render in-process with pypdfium2 -- but it
# stays so the index can be rebuilt from inside this image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
# Editable install: `purser_api/main.py` resolves `web/dist` by walking up
# from its own __file__ to the repo root (parent x3: purser_api -> src ->
# repo root). A normal `pip install .` copies the package into
# site-packages, losing that `src/` layer, so the path walk lands in
# site-packages instead of /app and the PWA silently 404s. `-e .` keeps
# __file__ pointing at /app/src/purser_api/main.py, matching the layout the
# app assumes (and how it's already run in dev via `uv sync`).
RUN pip install --no-cache-dir -e .

# The committed index. No ingest at build time.
COPY data/ ./data/

# The manual itself: needed at runtime by pdftoppm for citation page images.
# Not in git (controlled document, docs/*.pdf is gitignored) -- it must be
# present locally in docs/ to build this image.
COPY docs/*.pdf ./docs/

COPY --from=web /web/dist ./web/dist

# Warm the embedding model into the image so the first request isn't a download.
#
# FASTEMBED_CACHE_PATH must be set BEFORE the warm-up and must persist into the
# runtime env. Verified in fastembed 0.8.0 (`fastembed/common/utils.py`,
# `define_cache_dir`): with no cache_dir and no env var it defaults to
# `<tempdir>/fastembed_cache` -- so the warm-up would land in a temp directory,
# be discarded with the build layer, and the first real request would pay the
# download anyway. That is the cold-start cost this architecture explicitly
# pays money to avoid, so pin it.
ENV FASTEMBED_CACHE_PATH=/app/.fastembed
RUN python -c "from purser_core.embed import Embedder; Embedder()"

# Verify the warm-up actually persisted; fail the build loudly if it did not.
RUN test -d /app/.fastembed && test -n "$(ls -A /app/.fastembed)"

ENV PURSER_DATA_DIR=/app/data \
    PURSER_VAR_DIR=/app/var \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "purser_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
