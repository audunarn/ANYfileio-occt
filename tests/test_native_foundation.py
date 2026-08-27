"""Focused fake tests for the capability-zero native foundation."""

from __future__ import annotations

import gc
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
CORE_SOURCE_ROOT = Path(
    os.environ.get("ANYFILEIO_SOURCE_ROOT", ROOT.parent / "ANYfileIO" / "src")
)


@pytest.fixture(autouse=True)
def _reset_private_state() -> Any:
    from anyfileio_occt import _binding, _locking

    _binding._reset_binding_cache_for_tests()
    _locking._reset_global_settings_for_tests()
    yield
    _binding._reset_binding_cache_for_tests()
    _locking._reset_global_settings_for_tests()


def test_package_backend_and_factory_remain_native_lazy() -> None:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(SOURCE_ROOT), str(CORE_SOURCE_ROOT))
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            r'''
import importlib.abc
import sys

blocked = {"OCP", "cadquery", "anygeometry"}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError(f"blocked native or geometry import: {fullname}")
        return None

sys.meta_path.insert(0, Blocker())
import anyfileio_occt
import anyfileio_occt._binding
import anyfileio_occt._locking
import anyfileio_occt._session
import anyfileio_occt._units
from anyfileio.cad import CadCapabilities
from anyfileio_occt.backend import get_backend

backend = get_backend()
assert anyfileio_occt.__version__ == "0.1.1"
assert backend is get_backend()
assert backend.capabilities == CadCapabilities()
assert not any(name.split(".")[0] in blocked for name in sys.modules)
''',
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_binding_loader_uses_exact_distribution_and_namespace(monkeypatch) -> None:
    from anyfileio_occt import _binding

    module = ModuleType("OCP")
    calls: list[tuple[str, str]] = []

    def version(name: str) -> str:
        calls.append(("metadata", name))
        return "7.9.3.1.1"

    def load(name: str) -> ModuleType:
        calls.append(("import", name))
        return module

    monkeypatch.setattr(_binding.metadata, "version", version)
    monkeypatch.setattr(_binding.importlib, "import_module", load)
    result = _binding._load_binding()
    assert calls == [
        ("metadata", "cadquery-ocp-novtk"),
        ("import", "OCP"),
    ]
    assert result.distribution_name == "cadquery-ocp-novtk"
    assert result.distribution_version == "7.9.3.1.1"
    assert result.module is module


def test_binding_version_range_and_runtime_version_are_not_conflated(monkeypatch) -> None:
    from anyfileio.cad import BackendLoadError
    from anyfileio_occt import _binding

    imports: list[str] = []
    monkeypatch.setattr(
        _binding.importlib,
        "import_module",
        lambda name: imports.append(name) or ModuleType(name),
    )
    for rejected in (
        "7.9.3.1",
        "7.10",
        "7.9.3.1.1rc1",
        "7.9.3.1.1.dev1",
        "7.9.3.1.1+local",
        "not-a-version",
    ):
        _binding._reset_binding_cache_for_tests()
        monkeypatch.setattr(_binding.metadata, "version", lambda name, value=rejected: value)
        with pytest.raises(BackendLoadError) as caught:
            _binding._load_binding()
        assert caught.value.code == "cad.backend.load_failed"
        assert caught.value.diagnostic.details["version"] == rejected
    assert imports == []

    _binding._reset_binding_cache_for_tests()
    monkeypatch.setattr(_binding.metadata, "version", lambda name: "7.9.9")
    accepted = _binding._load_binding()
    assert accepted.distribution_version == "7.9.9"
    assert not hasattr(accepted, "occt_version")


def test_binding_success_and_terminal_failures_are_cached(monkeypatch) -> None:
    from anyfileio.cad import BackendLoadError
    from anyfileio_occt import _binding

    module = ModuleType("OCP")
    metadata_calls: list[str] = []
    import_calls: list[str] = []
    monkeypatch.setattr(
        _binding.metadata,
        "version",
        lambda name: metadata_calls.append(name) or "7.9.3.1.1",
    )
    monkeypatch.setattr(
        _binding.importlib,
        "import_module",
        lambda name: import_calls.append(name) or module,
    )
    first = _binding._load_binding()
    assert _binding._load_binding() is first
    assert metadata_calls == ["cadquery-ocp-novtk"]
    assert import_calls == ["OCP"]

    _binding._reset_binding_cache_for_tests()
    metadata_calls.clear()

    def missing(name: str) -> str:
        metadata_calls.append(name)
        raise _binding.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(_binding.metadata, "version", missing)
    with pytest.raises(BackendLoadError) as first_error:
        _binding._load_binding()
    with pytest.raises(BackendLoadError) as second_error:
        _binding._load_binding()
    assert second_error.value is first_error.value
    assert metadata_calls == ["cadquery-ocp-novtk"]


def test_binding_loader_never_falls_back_to_cadquery(monkeypatch) -> None:
    from anyfileio.cad import BackendLoadError
    from anyfileio_occt import _binding

    imports: list[str] = []
    monkeypatch.setattr(_binding.metadata, "version", lambda name: "7.9.3.1.1")

    def fail(name: str) -> ModuleType:
        imports.append(name)
        raise ImportError(name)

    monkeypatch.setattr(_binding.importlib, "import_module", fail)
    with pytest.raises(BackendLoadError) as first:
        _binding._load_binding()
    with pytest.raises(BackendLoadError) as second:
        _binding._load_binding()
    assert second.value is first.value
    assert imports == ["OCP"]


def test_global_guard_is_reentrant_and_restores_exact_values() -> None:
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt._locking import _SettingBinding, _global_settings

    state: dict[str, object] = {"a": "old-a", "b": ("old", "b")}
    log: list[tuple[str, str, object]] = []

    def binding(name: str) -> _SettingBinding:
        def get() -> object:
            log.append(("get", name, state[name]))
            return state[name]

        def set_value(value: object) -> None:
            log.append(("set", name, value))
            state[name] = value

        return _SettingBinding(name, get, set_value)

    bindings = (binding("a"), binding("b"))
    cancellations: list[dict[str, object]] = []
    with _global_settings(
        bindings,
        {"a": "outer-a", "b": ("outer", "b")},
        cancellation=lambda: cancellations.append(dict(state)) or False,
    ):
        assert state == {"a": "outer-a", "b": ("outer", "b")}
        with _global_settings(bindings, {"a": "inner-a"}):
            assert state == {"a": "inner-a", "b": ("outer", "b")}
        assert state == {"a": "outer-a", "b": ("outer", "b")}
    assert state == {"a": "old-a", "b": ("old", "b")}
    assert len(cancellations) == 8
    assert cancellations[-1] == {"a": "old-a", "b": ("old", "b")}
    assert [item[1:] for item in log if item[0] == "set"] == [
        ("a", "outer-a"),
        ("b", ("outer", "b")),
        ("a", "inner-a"),
        ("a", "outer-a"),
        ("b", ("old", "b")),
        ("a", "old-a"),
    ]

    cancelled_state: dict[str, object] = {"a": "old-a", "b": "old-b"}
    cancelled_sets: list[tuple[str, object]] = []
    cancelled_checks: list[dict[str, object]] = []

    def cancelled_binding(name: str) -> _SettingBinding:
        def get() -> object:
            return cancelled_state[name]

        def set_value(value: object) -> None:
            cancelled_sets.append((name, value))
            cancelled_state[name] = value

        return _SettingBinding(name, get, set_value)

    def cancel_before_native_window() -> bool:
        cancelled_checks.append(dict(cancelled_state))
        return len(cancelled_checks) == 7

    body_entered = False
    with pytest.raises(CadOperationCancelled) as caught:
        with _global_settings(
            (cancelled_binding("a"), cancelled_binding("b")),
            {"a": "new-a", "b": "new-b"},
            cancellation=cancel_before_native_window,
        ):
            body_entered = True
    assert caught.value.code == "cad.operation.cancelled"
    assert not body_entered
    assert cancelled_checks[6] == {"a": "new-a", "b": "new-b"}
    assert cancelled_checks[7] == {"a": "old-a", "b": "old-b"}
    assert cancelled_sets == [
        ("a", "new-a"),
        ("b", "new-b"),
        ("b", "old-b"),
        ("a", "old-a"),
    ]
    assert cancelled_state == {"a": "old-a", "b": "old-b"}


def test_global_guard_serializes_threads_and_unwinds_partial_apply() -> None:
    from anyfileio_occt._locking import _SettingBinding, _global_settings

    state = {"value": "original"}
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    order: list[str] = []
    setting = _SettingBinding(
        "value",
        lambda: state["value"],
        lambda value: state.__setitem__("value", value),
    )

    def first_worker() -> None:
        with _global_settings((setting,), {"value": "first"}):
            order.append("first-enter")
            first_entered.set()
            assert release_first.wait(1.0)
            order.append("first-exit")

    def second_worker() -> None:
        assert first_entered.wait(1.0)
        with _global_settings((setting,), {"value": "second"}):
            order.append("second-enter")
            second_entered.set()

    first_thread = threading.Thread(target=first_worker)
    second_thread = threading.Thread(target=second_worker)
    first_thread.start()
    second_thread.start()
    assert first_entered.wait(1.0)
    assert not second_entered.wait(0.05)
    release_first.set()
    first_thread.join(1.0)
    second_thread.join(1.0)
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert order == ["first-enter", "first-exit", "second-enter"]
    assert state["value"] == "original"

    values: dict[str, object] = {"a": "old-a", "b": "old-b"}
    restore_order: list[tuple[str, object]] = []

    def setter(name: str) -> Any:
        def set_value(value: object) -> None:
            values[name] = value
            restore_order.append((name, value))
            if name == "b" and value == "explode-after-mutation":
                raise RuntimeError("setter failed")

        return set_value

    bindings = tuple(
        _SettingBinding(name, lambda name=name: values[name], setter(name))
        for name in ("a", "b")
    )
    with pytest.raises(RuntimeError, match="setter failed"):
        with _global_settings(
            bindings,
            {"a": "new-a", "b": "explode-after-mutation"},
        ):
            raise AssertionError("unreachable")
    assert values == {"a": "old-a", "b": "old-b"}
    assert restore_order[-2:] == [("b", "old-b"), ("a", "old-a")]


def test_global_guard_preserves_primary_and_reports_restore_failure() -> None:
    from anyfileio.cad import BackendLoadError
    from anyfileio_occt._locking import (
        _SettingBinding,
        _global_settings,
        _reset_global_settings_for_tests,
    )

    clean_state = {"value": "old"}
    clean_trace: list[str] = []
    cancellation_calls = 0

    def clean_set(value: object) -> None:
        clean_state["value"] = value
        clean_trace.append(f"set:{value}")

    def cancel_after_restore() -> bool:
        nonlocal cancellation_calls
        cancellation_calls += 1
        clean_trace.append(f"cancel:{clean_state['value']}")
        # Five checks occur before the guarded body.  Cancel at the cleanup
        # checkpoint so the body's exception remains primary.
        return cancellation_calls == 6

    clean_setting = _SettingBinding(
        "value", lambda: clean_state["value"], clean_set
    )
    with pytest.raises(ValueError, match="body is primary") as cancelled_primary:
        with _global_settings(
            (clean_setting,),
            {"value": "new"},
            cancellation=cancel_after_restore,
        ):
            raise ValueError("body is primary")
    assert clean_state["value"] == "old"
    assert clean_trace[-2:] == ["set:old", "cancel:old"]
    assert any(
        "post-restoration cancellation checkpoint failed" in note
        and "CadOperationCancelled" in note
        for note in cancelled_primary.value.__notes__
    )

    state = {"value": "old"}
    restore_trace: list[str] = []

    def set_value(value: object) -> None:
        restore_trace.append(f"set:{value}")
        if value == "old":
            raise RuntimeError("restore broke")
        state["value"] = value

    setting = _SettingBinding("value", lambda: state["value"], set_value)
    with pytest.raises(ValueError, match="body is primary") as primary:
        with _global_settings(
            (setting,),
            {"value": "new"},
            cancellation=lambda: restore_trace.append("cancel") or False,
        ):
            raise ValueError("body is primary")
    assert any("restore broke" in note for note in primary.value.__notes__)
    assert restore_trace[-1] == "set:old"

    callbacks: list[str] = []
    forbidden = _SettingBinding(
        "forbidden",
        lambda: callbacks.append("getter") or "old",
        lambda value: callbacks.append("setter"),
    )
    with pytest.raises(BackendLoadError) as poisoned:
        with _global_settings(
            (forbidden,),
            {"forbidden": "new"},
            cancellation=lambda: callbacks.append("cancellation") or False,
        ):
            callbacks.append("body")
    assert poisoned.value.code == "cad.backend.load_failed"
    assert callbacks == []

    _reset_global_settings_for_tests()
    state["value"] = "old"
    with pytest.raises(BackendLoadError) as close_only:
        with _global_settings((setting,), {"value": "new"}):
            pass
    assert close_only.value.code == "cad.backend.load_failed"


def test_session_is_thread_affine_reverse_ordered_and_idempotent() -> None:
    from anyfileio.cad import CadOperationError
    from anyfileio_occt._session import _NativeSession

    session = _NativeSession()
    closed: list[str] = []

    def closer(resource: object) -> None:
        closed.append(str(resource))
        if resource == "b":
            raise RuntimeError("b close failed")

    for resource in ("a", "b", "c"):
        assert session.acquire(resource, closer) == resource
    assert session.use("b") == "b"

    wrong_thread_errors: list[BaseException] = []

    def wrong_thread() -> None:
        for action in (lambda: session.use("a"), session.close):
            try:
                action()
            except BaseException as exc:
                wrong_thread_errors.append(exc)

    thread = threading.Thread(target=wrong_thread)
    thread.start()
    thread.join(1.0)
    assert [getattr(error, "code", None) for error in wrong_thread_errors] == [
        "cad.session.wrong_thread",
        "cad.session.wrong_thread",
    ]
    assert closed == []

    with pytest.raises(CadOperationError) as close_error:
        session.close()
    assert close_error.value.code == "cad.operation.failed"
    assert closed == ["c", "b", "a"]
    assert session.closed and session._resources == []
    session.close()
    assert closed == ["c", "b", "a"]

    primary_session = _NativeSession()
    primary_session.acquire("x", lambda resource: (_ for _ in ()).throw(RuntimeError("x close")))
    with pytest.raises(ValueError, match="body primary") as primary:
        with primary_session:
            raise ValueError("body primary")
    assert any("x close" in note for note in primary.value.__notes__)
    assert primary_session.closed


def test_session_partial_acquisition_unwinds_without_finalizer_native_calls() -> None:
    from anyfileio_occt._session import _NativeSession

    closed: list[str] = []
    session = _NativeSession()
    try:
        session.acquire("first", lambda resource: closed.append(str(resource)))
        session.acquire(
            "second",
            lambda resource: (
                closed.append(str(resource)),
                (_ for _ in ()).throw(RuntimeError("second close")),
            )[1],
        )
        raise LookupError("construction primary")
    except LookupError as primary:
        session.close(primary=primary)
        assert any("second close" in note for note in primary.__notes__)
    assert closed == ["second", "first"]
    assert session.closed and session._resources == []

    finalized_calls: list[str] = []
    abandoned = _NativeSession()
    abandoned.acquire("left", lambda resource: finalized_calls.append(str(resource)))
    with pytest.warns(ResourceWarning):
        abandoned.__del__()
    assert finalized_calls == []
    abandoned.close()
    assert finalized_calls == ["left"]
    del abandoned
    gc.collect()
    assert finalized_calls == ["left"]


def test_units_cover_exact_tokens_scales_unknown_and_override() -> None:
    from anyfileio_occt._units import _resolve_units

    expected = {
        "um": 1e-6,
        "mm": 1e-3,
        "cm": 1e-2,
        "m": 1.0,
        "km": 1000.0,
        "in": 0.0254,
        "ft": 0.3048,
    }
    for token, scale in expected.items():
        declared = _resolve_units(token, None)
        assert declared.declared_unit == token
        assert declared.effective_unit == token
        assert declared.source_to_metre_scale == scale
        assert not declared.override_supplied_missing
        assert _resolve_units(token, token) == declared

    for missing in (None, "unknown"):
        unresolved = _resolve_units(missing, None)
        assert unresolved.declared_unit == missing
        assert unresolved.effective_unit == "unknown"
        assert unresolved.source_to_metre_scale is None
        assert not unresolved.override_supplied_missing
        supplied = _resolve_units(missing, "mm")
        assert supplied.effective_unit == "mm"
        assert supplied.source_to_metre_scale == 1e-3
        assert supplied.override_supplied_missing


def test_units_reject_disagreement_and_forbid_inference() -> None:
    from anyfileio_occt._units import _resolve_units

    with pytest.raises(ValueError, match="disagree"):
        _resolve_units("m", "mm")
    for forbidden in ("MM", " mm ", "millimetre", "inch", "", 1):
        with pytest.raises(ValueError):
            _resolve_units(forbidden, None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            _resolve_units(None, forbidden)  # type: ignore[arg-type]
