"""Protocol-1 bootstrap shell for the optional OCCT backend.

This module intentionally contains no native binding or geometry integration.
The zero-capability shell gives core discovery a stable, fail-closed target for
later separately qualified provider slices.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from anyfileio.cad import (
    BackendLoadError,
    CadAssetWriteReport,
    CadCapabilities,
    CadDiagnostic,
    CadDocument,
    CadPrototypeMesh,
    CadReadOptions,
    CadTessellationOptions,
    CadWriteOptions,
    CancellationCheck,
)

__all__ = ["get_backend"]


def _not_implemented(operation: str) -> NoReturn:
    diagnostic = CadDiagnostic(
        "cad.backend.load_failed",
        "error",
        "the OCCT backend bootstrap implements no CAD operations",
        details={"operation": operation},
    )
    raise BackendLoadError(diagnostic=diagnostic)


class _OcctBootstrapBackend:
    backend_id = "occt"
    protocol_version = 1
    backend_compatibility_version = 1
    backend_version = "0.1.0"
    capabilities = CadCapabilities()

    def read(
        self,
        source_snapshot: Path,
        *,
        source_sha256: str,
        source_name: str,
        options: CadReadOptions,
        tessellation_options: CadTessellationOptions | None,
        cancellation: CancellationCheck,
    ) -> CadDocument:
        _not_implemented("read")

    def tessellate(
        self,
        document: CadDocument,
        *,
        options: CadTessellationOptions,
        cancellation: CancellationCheck,
    ) -> tuple[CadPrototypeMesh, ...]:
        _not_implemented("tessellate")

    def translate(
        self,
        document: CadDocument,
        destination_temporary: Path,
        *,
        options: CadWriteOptions,
        cancellation: CancellationCheck,
    ) -> CadAssetWriteReport:
        _not_implemented("translate")


_BACKEND = _OcctBootstrapBackend()


def get_backend() -> _OcctBootstrapBackend:
    """Return the process-wide zero-capability protocol shell."""

    return _BACKEND
