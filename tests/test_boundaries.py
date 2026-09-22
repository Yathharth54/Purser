"""purser_core must stay free of the web stack.

This is what keeps a future MCP adapter a day's work instead of a fork. Without
this test the boundary erodes silently and nobody notices until reuse is attempted.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FORBIDDEN = {"fastapi", "pydantic_ai", "openai", "httpx", "requests", "sqlmodel", "starlette"}
CORE = Path(__file__).resolve().parents[1] / "src" / "purser_core"
PATHS = sorted(CORE.rglob("*.py"))
assert PATHS, "boundary test found no core modules"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.name)
def test_core_does_not_import_the_web_stack(path: Path):
    leaked = _imported_roots(path) & FORBIDDEN
    assert not leaked, f"{path.name} imports {sorted(leaked)} — L2 must stay framework-free"
