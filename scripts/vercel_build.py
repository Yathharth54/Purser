"""Vercel build step: build the PWA and bake the embedding model into the bundle.

Runs on Vercel after Python dependencies are installed (see [tool.vercel.scripts]
in pyproject.toml). The model is downloaded HERE, at build time, into
./.models -- at runtime the function filesystem is read-only and a first-request
download would add seconds to a cold start and depend on Hugging Face being up.
The runtime sets FASTEMBED_CACHE_PATH to this directory and HF_HUB_OFFLINE=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / ".models"


def _flatten(cache: Path) -> None:
    """Keep one real copy of each model file.

    The Hugging Face cache stores each file as a blob plus symlinks to it, and
    the bundler follows symlinks: the 64 MB model counted as 192 MB and pushed
    the function past Vercel's 500 MB limit. Replace each symlink with the file
    it points to, then drop the blob stores. Loading offline still works --
    the snapshot directory is all that is read.
    """
    for link in [p for p in cache.rglob("*") if p.is_symlink()]:
        target = link.resolve()
        link.unlink()
        shutil.copy2(target, link)
    for d in [cache / "blobs", cache / ".locks", *cache.glob("models--*/blobs")]:
        shutil.rmtree(d, ignore_errors=True)


def main() -> None:
    subprocess.run(["npm", "ci"], cwd=ROOT / "web", check=True)
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True)

    os.environ["FASTEMBED_CACHE_PATH"] = str(MODELS)
    from fastembed import TextEmbedding

    from purser_core.embed import MODEL_NAME

    TextEmbedding(model_name=MODEL_NAME, cache_dir=str(MODELS))
    _flatten(MODELS)
    if not any(MODELS.rglob("*.onnx")):
        raise SystemExit(f"embedding model did not land in {MODELS}")
    print(f"model baked into {MODELS}")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    main()
