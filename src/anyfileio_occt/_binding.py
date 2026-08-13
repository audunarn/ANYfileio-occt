"""Lazy, fail-closed access to the optional OCCT Python binding."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from importlib import metadata
from types import ModuleType
from threading import Lock

from anyfileio.cad import BackendLoadError, CadDiagnostic


_DISTRIBUTION_NAME = "cadquery-ocp-novtk"
_IMPORT_NAMESPACE = "OCP"
_MINIMUM_VERSION = (7, 9, 3, 1, 1)
_MAXIMUM_VERSION = (7, 10)


@dataclass(frozen=True, slots=True)
class _Binding:
    distribution_name: str
    distribution_version: str
    module: ModuleType


_CACHE_LOCK = Lock()
_CACHED_BINDING: _Binding | None = None
_CACHED_ERROR: BackendLoadError | None = None


def _load_error(message: str, *, details: dict[str, str]) -> BackendLoadError:
    return BackendLoadError(
        diagnostic=CadDiagnostic(
            "cad.backend.load_failed",
            "error",
            message,
            details=details,
        )
    )


def _numeric_version(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    if not parts or any(not part or not part.isascii() or not part.isdecimal() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def _load_binding() -> _Binding:
    """Load and cache the one supported binding distribution and namespace."""

    global _CACHED_BINDING, _CACHED_ERROR
    with _CACHE_LOCK:
        if _CACHED_BINDING is not None:
            return _CACHED_BINDING
        if _CACHED_ERROR is not None:
            raise _CACHED_ERROR

        try:
            version = metadata.version(_DISTRIBUTION_NAME)
        except Exception as exc:
            error = _load_error(
                "the required OCCT binding distribution metadata is unavailable",
                details={"distribution": _DISTRIBUTION_NAME, "stage": "metadata"},
            )
            _CACHED_ERROR = error
            raise error from exc

        parsed = _numeric_version(version)
        if (
            parsed is None
            or _compare_versions(parsed, _MINIMUM_VERSION) < 0
            or _compare_versions(parsed, _MAXIMUM_VERSION) >= 0
        ):
            error = _load_error(
                "the OCCT binding distribution version is unsupported",
                details={
                    "distribution": _DISTRIBUTION_NAME,
                    "stage": "version",
                    "version": version,
                },
            )
            _CACHED_ERROR = error
            raise error

        try:
            module = importlib.import_module(_IMPORT_NAMESPACE)
        except Exception as exc:
            error = _load_error(
                "the OCCT binding namespace could not be imported",
                details={
                    "distribution": _DISTRIBUTION_NAME,
                    "namespace": _IMPORT_NAMESPACE,
                    "stage": "import",
                    "version": version,
                },
            )
            _CACHED_ERROR = error
            raise error from exc

        binding = _Binding(_DISTRIBUTION_NAME, version, module)
        _CACHED_BINDING = binding
        return binding


def _reset_binding_cache_for_tests() -> None:
    """Reset only the private binding cache for isolated fake tests."""

    global _CACHED_BINDING, _CACHED_ERROR
    with _CACHE_LOCK:
        _CACHED_BINDING = None
        _CACHED_ERROR = None
