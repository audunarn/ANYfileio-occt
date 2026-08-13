"""Thread-affine ownership for future native OCCT resources."""

from __future__ import annotations

import threading
import warnings
from typing import Callable

from anyfileio.cad import CadDiagnostic, CadOperationError


_Closer = Callable[[object], None]


def _operation_failure(message: str) -> CadOperationError:
    return CadOperationError(
        diagnostic=CadDiagnostic("cad.operation.failed", "error", message)
    )


class _NativeSession:
    """Own a LIFO stack of resources on exactly one Python thread."""

    __slots__ = ("_closed", "_owner_thread", "_resources")

    def __init__(self) -> None:
        self._owner_thread = threading.get_ident()
        self._resources: list[tuple[object, _Closer]] = []
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise CadOperationError(
                diagnostic=CadDiagnostic(
                    "cad.session.wrong_thread",
                    "error",
                    "the native CAD session was used from a non-owner thread",
                )
            )

    def acquire(self, resource: object, closer: _Closer) -> object:
        self._check_owner()
        if self._closed:
            raise _operation_failure("the native CAD session is already closed")
        self._resources.append((resource, closer))
        return resource

    def use(self, resource: object) -> object:
        """Establish an owner-checked boundary before a later native use."""

        self._check_owner()
        if self._closed:
            raise _operation_failure("the native CAD session is already closed")
        if not any(owned is resource for owned, _ in self._resources):
            raise _operation_failure("the resource is not owned by this native CAD session")
        return resource

    def close(self, *, primary: BaseException | None = None) -> None:
        self._check_owner()
        if self._closed:
            return

        failures: list[BaseException] = []
        try:
            while self._resources:
                resource, closer = self._resources.pop()
                try:
                    closer(resource)
                except BaseException as exc:
                    failures.append(exc)
        finally:
            self._resources.clear()
            self._closed = True

        if not failures:
            return
        if primary is not None:
            for failure in failures:
                primary.add_note(f"native CAD session cleanup failed: {failure!r}")
            return

        error = _operation_failure("one or more native CAD session resources failed to close")
        for failure in failures:
            error.add_note(f"native CAD session cleanup failed: {failure!r}")
        raise error from failures[0]

    def __enter__(self) -> "_NativeSession":
        self._check_owner()
        if self._closed:
            raise _operation_failure("the native CAD session is already closed")
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        self.close(primary=exception)
        return False

    def __del__(self) -> None:
        if not getattr(self, "_closed", True) and getattr(self, "_resources", ()):
            warnings.warn(
                "an unclosed native CAD session was finalized without invoking native closers",
                ResourceWarning,
                stacklevel=2,
            )
