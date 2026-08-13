"""Reversible serialization for future process-global OCCT settings."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Iterator, Mapping

from anyfileio.cad import (
    BackendLoadError,
    CadDiagnostic,
    CadOperationCancelled,
    CancellationCheck,
)


@dataclass(frozen=True, slots=True)
class _SettingBinding:
    name: str
    getter: Callable[[], object]
    setter: Callable[[object], None]


_GLOBAL_LOCK = RLock()
_POISON_ERROR: BackendLoadError | None = None


def _backend_failure(message: str) -> BackendLoadError:
    return BackendLoadError(
        diagnostic=CadDiagnostic("cad.backend.load_failed", "error", message)
    )


def _raise_if_poisoned() -> None:
    if _POISON_ERROR is not None:
        raise _POISON_ERROR


def _check_cancellation(cancellation: CancellationCheck) -> None:
    if cancellation is not None and cancellation():
        raise CadOperationCancelled(
            diagnostic=CadDiagnostic(
                "cad.operation.cancelled",
                "error",
                "the CAD operation was cancelled",
            )
        )


def _record_cleanup_notes(primary: BaseException, failures: list[tuple[str, BaseException]]) -> None:
    for name, failure in failures:
        primary.add_note(f"failed to restore global setting {name!r}: {failure!r}")


def _restore(
    applied: list[tuple[_SettingBinding, object]],
) -> list[tuple[str, BaseException]]:
    failures: list[tuple[str, BaseException]] = []
    while applied:
        binding, prior = applied.pop()
        try:
            binding.setter(prior)
        except BaseException as exc:
            failures.append((binding.name, exc))
    return failures


def _poison(failures: list[tuple[str, BaseException]]) -> BackendLoadError:
    global _POISON_ERROR
    if _POISON_ERROR is None:
        error = _backend_failure(
            "an OCCT process-global setting could not be restored; the guard is poisoned"
        )
        for name, failure in failures:
            error.add_note(f"failed to restore global setting {name!r}: {failure!r}")
        _POISON_ERROR = error
    return _POISON_ERROR


@contextmanager
def _global_settings(
    bindings: tuple[_SettingBinding, ...],
    overrides: Mapping[str, object],
    *,
    cancellation: CancellationCheck = None,
) -> Iterator[None]:
    """Apply declared overrides under the one process-global reversible lock."""

    _raise_if_poisoned()
    _check_cancellation(cancellation)
    with _GLOBAL_LOCK:
        _raise_if_poisoned()
        _check_cancellation(cancellation)

        snapshots: list[tuple[_SettingBinding, object]] = []
        applied: list[tuple[_SettingBinding, object]] = []
        try:
            for binding in bindings:
                _check_cancellation(cancellation)
                snapshots.append((binding, binding.getter()))
            for binding, prior in snapshots:
                if binding.name in overrides:
                    _check_cancellation(cancellation)
                    # Register before the call: a setter may mutate and then fail.
                    applied.append((binding, prior))
                    binding.setter(overrides[binding.name])
            _check_cancellation(cancellation)
            yield
        except BaseException as primary:
            failures = _restore(applied)
            if failures:
                _poison(failures)
                _record_cleanup_notes(primary, failures)
            else:
                try:
                    _check_cancellation(cancellation)
                except BaseException as cancellation_failure:
                    primary.add_note(
                        "post-restoration cancellation checkpoint failed: "
                        f"{cancellation_failure!r}"
                    )
            raise
        else:
            failures = _restore(applied)
            if failures:
                raise _poison(failures) from failures[0][1]
            _check_cancellation(cancellation)


def _reset_global_settings_for_tests() -> None:
    """Clear only the process guard poison for isolated fake tests."""

    global _POISON_ERROR
    with _GLOBAL_LOCK:
        _POISON_ERROR = None
