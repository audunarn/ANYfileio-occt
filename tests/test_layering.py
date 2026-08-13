"""Static import-boundary checks for the bootstrap provider."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "anyfileio_occt"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_provider_source_imports_only_stdlib_and_anyfileio() -> None:
    allowed = {"__future__", "pathlib", "typing", "anyfileio"}
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        assert _imports(path) <= allowed, path
        text = path.read_text(encoding="utf-8")
        assert "import OCP" not in text
        assert "import cadquery" not in text
        assert "import anygeometry" not in text


def test_no_native_geometry_or_future_provider_modules_exist() -> None:
    assert {path.name for path in PACKAGE_ROOT.iterdir()} == {
        "__init__.py",
        "backend.py",
    }
    forbidden = {
        "document.py",
        "xde.py",
        "step.py",
        "iges.py",
        "brep.py",
        "units.py",
        "locking.py",
        "diagnostics.py",
        "arrays.py",
        "prototypes.py",
        "tessellation.py",
        "geometry_export.py",
    }
    assert not forbidden.intersection(path.name for path in PACKAGE_ROOT.iterdir())
