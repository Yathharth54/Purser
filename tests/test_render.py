from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from purser_ingest.render import render_page


@pytest.fixture
def var_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    return tmp_path


def _stub_pdftoppm(monkeypatch, calls: list | None = None):
    """Fakes pdftoppm by dropping a tiny real PNG next to the requested stem."""

    def fake_run(cmd, check, capture_output):  # noqa: ARG001 - signature must match the real call
        if calls is not None:
            calls.append(cmd)
        stem = Path(cmd[-1])
        Image.new("RGB", (4, 4)).save(stem.with_suffix(".png"))

    monkeypatch.setattr("purser_ingest.render.subprocess.run", fake_run)


def test_render_page_names_the_cache_file_by_page_number(var_dir, monkeypatch):
    _stub_pdftoppm(monkeypatch)
    out = render_page(Path("dummy.pdf"), 7)
    assert out == var_dir / "pagecache" / "p0007.webp"
    assert out.is_file()


def test_render_page_caches_and_only_shells_out_once(var_dir, monkeypatch):
    """A second call for the same page must hit the on-disk cache.

    Kills the mutant that drops the `if out.is_file(): return out` guard --
    without it, every request for an already-rendered page would re-invoke
    pdftoppm, defeating the whole point of caching.
    """
    calls: list = []
    _stub_pdftoppm(monkeypatch, calls)

    first = render_page(Path("dummy.pdf"), 42)
    second = render_page(Path("dummy.pdf"), 42)

    assert first == second
    assert len(calls) == 1


def test_render_page_removes_the_intermediate_png(var_dir, monkeypatch):
    """Kills the mutant that drops `png.unlink(missing_ok=True)`, which would
    leave a duplicate, uncompressed PNG behind for every page ever rendered.
    """
    _stub_pdftoppm(monkeypatch)
    out = render_page(Path("dummy.pdf"), 3)
    assert not out.with_suffix(".png").exists()


def test_render_page_propagates_pdftoppm_failure(var_dir, monkeypatch):
    def fake_run(cmd, check, capture_output):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("purser_ingest.render.subprocess.run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        render_page(Path("dummy.pdf"), 999)
