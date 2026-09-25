"""Render every page of the manual and upload it to the private Blob store.

Run once per manual revision, from a machine that has the PDF:

    uv run python scripts/upload_pages.py "docs/<manual>.pdf" --token-file .env.blob

where .env.blob (gitignored) holds the store's BLOB_READ_WRITE_TOKEN=... line.

The deployed app serves page images from these (see purser_api.pages), so the
PDF itself never leaves this machine. Pages already in the store are skipped,
so a re-run after an interruption only uploads what is missing; pass
--replace after a reissue to overwrite them all.

Budget, on the Hobby plan (1 GB storage, 2,000 uploads a month): ~92 MB and
one upload per page, 1,226 in all.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from purser_api.pages import BLOB_PREFIX, blob_path  # noqa: E402

YEAR = 365 * 24 * 3600


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--replace", action="store_true", help="overwrite pages already stored")
    parser.add_argument("--dry-run", action="store_true", help="render and count, upload nothing")
    parser.add_argument(
        "--token-file",
        type=Path,
        help="a file holding BLOB_READ_WRITE_TOKEN=..., so the token never sits on a command line",
    )
    args = parser.parse_args()
    if args.token_file:
        for line in args.token_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "BLOB_READ_WRITE_TOKEN":
                os.environ["BLOB_READ_WRITE_TOKEN"] = value.strip().strip('"').strip("'")
    if not os.environ.get("BLOB_READ_WRITE_TOKEN") and not args.dry_run:
        sys.exit("BLOB_READ_WRITE_TOKEN is not set")

    # Render into a scratch cache, never the app's own.
    os.environ["PURSER_VAR_DIR"] = tempfile.mkdtemp(prefix="purser-pages-")
    import pypdfium2 as pdfium
    from vercel.blob import iter_objects, put

    from purser_ingest.render import render_page

    total = len(pdfium.PdfDocument(args.pdf))
    stored: set[str] = set()
    if not args.replace and not args.dry_run:
        stored = {item.pathname for item in iter_objects(prefix=f"{BLOB_PREFIX}/")}
    todo = [n for n in range(1, total + 1) if blob_path(n) not in stored]
    print(f"{total} pages, {len(stored)} already stored, {len(todo)} to upload", flush=True)

    sent_bytes = 0
    for i, n in enumerate(todo, start=1):
        image = render_page(args.pdf, n).read_bytes()
        sent_bytes += len(image)
        if not args.dry_run:
            put(
                blob_path(n),
                image,
                access="private",
                content_type="image/webp",
                overwrite=args.replace,
                cache_control_max_age=YEAR,
            )
        if i % 100 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  {sent_bytes / 1_048_576:.1f} MB", flush=True)
    print("done" if not args.dry_run else "dry run: nothing uploaded")


if __name__ == "__main__":
    main()
