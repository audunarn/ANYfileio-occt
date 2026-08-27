"""Focused source checks for the capability-zero provider bootstrap."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
CORE_SOURCE_ROOT = Path(
    os.environ.get("ANYFILEIO_SOURCE_ROOT", ROOT.parent / "ANYfileIO" / "src")
)


def _metadata() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def _subprocess(code: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(SOURCE_ROOT), str(CORE_SOURCE_ROOT)))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_project_metadata_and_entry_point_are_frozen() -> None:
    metadata = _metadata()
    project = metadata["project"]
    assert project["name"] == "ANYfileio-occt"
    assert project["version"] == "0.1.1"
    assert project["requires-python"] == ">=3.11,<3.15"
    assert project["dependencies"] == [
        "ANYfileio>=0.2.1,<0.3",
        "numpy>=1.26",
        "cadquery-ocp-novtk>=7.9.3.1.1,<7.10",
    ]
    assert project["optional-dependencies"]["geometry"] == ["ANYgeometry>=0.4.1,<0.5"]
    assert project["optional-dependencies"]["dev"] == ["pytest>=8"]
    assert project["entry-points"] == {
        "anyfileio.backends": {"occt": "anyfileio_occt.backend:get_backend"}
    }
    assert metadata["tool"]["setuptools"]["package-dir"] == {"": "src"}
    assert metadata["tool"]["setuptools"]["packages"]["find"] == {
        "where": ["src"],
        "include": ["anyfileio_occt*"],
    }


def test_license_is_protected_and_metadata_is_minimal() -> None:
    license_path = ROOT / "LICENSE"
    assert hashlib.sha256(license_path.read_bytes()).hexdigest() == (
        "230184f60bae2feaf244f10a8bac053c8ff33a183bcc365b4d8b876d2b7f4809"
    )
    metadata = _metadata()
    assert metadata["project"]["license"] == {"file": "LICENSE"}
    assert "package-data" not in metadata["tool"]["setuptools"]
    assert {
        path.name for path in ROOT.iterdir() if path.name != ".pytest_cache"
    } == {
        ".git",
        ".github",
        ".gitignore",
        "ECOSYSTEM_GUIDE.md",
        "LICENSE",
        "pyproject.toml",
        "src",
        "tests",
    }


def test_package_import_is_core_and_native_independent() -> None:
    completed = _subprocess(
        r"""
import importlib.abc
import sys

blocked = {"anyfileio", "OCP", "cadquery", "anygeometry"}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError(f"blocked bootstrap dependency: {fullname}")
        return None

sys.meta_path.insert(0, Blocker())
import anyfileio_occt
assert anyfileio_occt.__version__ == "0.1.1"
assert not hasattr(anyfileio_occt, "get_backend")
assert not any(name.split(".")[0] in blocked for name in sys.modules)
"""
    )
    assert completed.returncode == 0, completed.stderr


def test_backend_and_factory_import_under_blocker() -> None:
    completed = _subprocess(
        r"""
import importlib.abc
import sys

blocked = {"OCP", "cadquery", "anygeometry"}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError(f"blocked native or geometry import: {fullname}")
        return None

sys.meta_path.insert(0, Blocker())
from anyfileio_occt.backend import get_backend
first = get_backend()
second = get_backend()
assert first is second
assert not any(name.split(".")[0] in blocked for name in sys.modules)
"""
    )
    assert completed.returncode == 0, completed.stderr


def test_factory_is_singleton_with_exact_identity_and_zero_capabilities() -> None:
    from anyfileio.cad import CadCapabilities
    from anyfileio_occt.backend import get_backend

    first = get_backend()
    assert first is get_backend()
    assert first.backend_id == "occt"
    assert first.protocol_version == 1
    assert first.backend_compatibility_version == 1
    assert first.backend_version == "0.1.1"
    assert first.capabilities == CadCapabilities()


def test_protocol_shell_has_exact_call_shapes() -> None:
    from anyfileio_occt.backend import get_backend

    backend = get_backend()
    expected = {
        "read": (
            ("source_snapshot", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("source_sha256", inspect.Parameter.KEYWORD_ONLY),
            ("source_name", inspect.Parameter.KEYWORD_ONLY),
            ("options", inspect.Parameter.KEYWORD_ONLY),
            ("tessellation_options", inspect.Parameter.KEYWORD_ONLY),
            ("cancellation", inspect.Parameter.KEYWORD_ONLY),
        ),
        "tessellate": (
            ("document", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("options", inspect.Parameter.KEYWORD_ONLY),
            ("cancellation", inspect.Parameter.KEYWORD_ONLY),
        ),
        "translate": (
            ("document", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("destination_temporary", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("options", inspect.Parameter.KEYWORD_ONLY),
            ("cancellation", inspect.Parameter.KEYWORD_ONLY),
        ),
    }
    for name, wanted in expected.items():
        parameters = inspect.signature(getattr(backend, name)).parameters.values()
        assert tuple((item.name, item.kind) for item in parameters) == wanted


def test_protocol_stubs_fail_typed_before_io() -> None:
    from anyfileio.cad import BackendLoadError, CadCapabilities
    from anyfileio_occt.backend import get_backend

    backend = get_backend()
    calls = (
        (
            "read",
            lambda: backend.read(
                object(),
                source_sha256="not-inspected",
                source_name="not-inspected",
                options=object(),
                tessellation_options=object(),
                cancellation=lambda: (_ for _ in ()).throw(AssertionError("called")),
            ),
        ),
        (
            "tessellate",
            lambda: backend.tessellate(
                object(),
                options=object(),
                cancellation=lambda: (_ for _ in ()).throw(AssertionError("called")),
            ),
        ),
        (
            "translate",
            lambda: backend.translate(
                object(),
                object(),
                options=object(),
                cancellation=lambda: (_ for _ in ()).throw(AssertionError("called")),
            ),
        ),
    )
    for operation, invoke in calls:
        with pytest.raises(BackendLoadError) as caught:
            invoke()
        assert caught.value.code == "cad.backend.load_failed"
        assert caught.value.diagnostic.details == {"operation": operation}
    assert backend.capabilities == CadCapabilities()


@dataclass
class _Distribution:
    name: str = "ANYfileio-occt"


class _EntryPoint:
    group = "anyfileio.backends"
    name = "occt"
    value = "anyfileio_occt.backend:get_backend"
    dist = _Distribution()

    def __init__(self) -> None:
        self.load_calls = 0

    def load(self) -> Any:
        self.load_calls += 1
        return importlib.import_module("anyfileio_occt.backend").get_backend


class _EntryPoints(tuple):
    def select(self, *, group: str, name: str) -> tuple[_EntryPoint, ...]:
        return tuple(item for item in self if item.group == group and item.name == name)


def test_core_fake_entry_point_transitions_discovered_to_broken(monkeypatch) -> None:
    import anyfileio.cad_backend as discovery
    from anyfileio.cad import BackendLoadError, CadCapabilities
    from anyfileio_occt.backend import get_backend

    entry = _EntryPoint()
    monkeypatch.setattr(discovery.metadata, "entry_points", lambda: _EntryPoints((entry,)))
    backend = get_backend()
    operation_calls = [0]

    def forbidden(*args, **kwargs):
        operation_calls[0] += 1
        raise AssertionError("zero-capability shell operation was called")

    monkeypatch.setattr(backend, "read", forbidden)
    monkeypatch.setattr(backend, "tessellate", forbidden)
    monkeypatch.setattr(backend, "translate", forbidden)
    discovery._reset_backend_cache_for_tests()
    try:
        assert discovery.backend_status().state == "discovered"
        assert entry.load_calls == 0
        with pytest.raises(BackendLoadError) as first:
            discovery._load_backend()
        status = discovery.backend_status()
        assert first.value.code == "cad.backend.load_failed"
        assert status.state == "broken"
        assert status.capabilities == CadCapabilities()
        assert entry.load_calls == 1
        assert operation_calls == [0]
        with pytest.raises(BackendLoadError) as second:
            discovery._load_backend()
        assert second.value is first.value
        assert entry.load_calls == 1
        assert operation_calls == [0]
        assert not any(
            name.split(".")[0] in {"OCP", "cadquery", "anygeometry"}
            for name in sys.modules
        )
    finally:
        discovery._reset_backend_cache_for_tests()
