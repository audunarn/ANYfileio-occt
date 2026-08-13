"""Pure source-unit decisions for future OCCT readers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from anyfileio.cad import LengthUnit


_UnknownUnit = Literal["unknown"]
_CANONICAL_SCALES: dict[str, float] = {
    "um": 1e-6,
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
}


@dataclass(frozen=True, slots=True)
class _UnitDecision:
    declared_unit: LengthUnit | _UnknownUnit | None
    effective_unit: LengthUnit | _UnknownUnit
    source_to_metre_scale: float | None
    override_supplied_missing: bool


def _known_unit(value: object) -> bool:
    return isinstance(value, str) and value in _CANONICAL_SCALES


def _resolve_units(
    declared: LengthUnit | _UnknownUnit | None,
    override: LengthUnit | None,
) -> _UnitDecision:
    """Resolve canonical source units without aliases, inference, or scaling."""

    if declared is not None and declared != "unknown" and not _known_unit(declared):
        raise ValueError(f"unsupported declared length unit {declared!r}")
    if override is not None and not _known_unit(override):
        raise ValueError(f"unsupported length-unit override {override!r}")

    if declared not in (None, "unknown"):
        if override is not None and override != declared:
            raise ValueError("declared length unit and override disagree")
        return _UnitDecision(
            declared,
            declared,
            _CANONICAL_SCALES[declared],
            False,
        )

    if override is not None:
        return _UnitDecision(declared, override, _CANONICAL_SCALES[override], True)
    return _UnitDecision(declared, "unknown", None, False)
