"""Correction domain policy: process gain."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.domain.services.correction_actuator_selection import _normalize_ec_component_alias
from ae3lite.domain.services.correction_math_defaults import _EC_GAIN_COMPONENT_SKIP
from ae3lite.domain.services.correction_primitives import _coerce_ratio


def _ec_component_process_gain(
    *,
    component: str,
    process_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    phase_key: str,
) -> float | None:
    """Разрешает EC-gain для конкретного компонента с fallback на общий `ec_gain_per_ml`.

    Совместимость payload:
    - nested ``{calcium: {ec_gain_per_ml: N}}``
    - flat ``{calcium: N}`` (legacy UI)
    """
    gains = process_cfg.get("ec_component_gains")
    gains = gains if isinstance(gains, Mapping) else {}
    entry = gains.get(component)
    if isinstance(entry, (int, float)) and not isinstance(entry, bool):
        value = float(entry)
        if value > 0:
            return value
    if isinstance(entry, Mapping):
        raw = entry.get("ec_gain_per_ml")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            # Пока не применяем adaptive EMA: per-component gain остаётся авторитетным.
            return value
    return _process_gain(kind="ec", process_cfg=process_cfg, pid_entry=pid_entry, phase_key=phase_key)


def effective_process_gain(
    *,
    kind: str,
    process_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    phase_key: str,
    component: str | None = None,
) -> float | None:
    """Authoritative ⊕ learned process gain used by dose planning and no-effect thresholds.

    Same algorithm as the planner pulse sizing path: blend learned EMA into the
    calibrated gain with retention/wave weighting, clamp to 0.25×–4× of auth,
    and apply the tank_recirc EC floor (learned may raise confidence but must
    not shrink auth gain and inflate the next impulse).

    For a forced EC component, ``component`` selects ``ec_component_gains`` and
    falls back to generic ``ec_gain_per_ml`` only when that component has no
    positive gain. Per-component auth gain is not blended with the generic EMA.

    Shared with ``ObservationAnalyzer.expected_effect`` so the no-effect
    threshold uses the identical effective gain the planner used for the dose.
    """
    if kind == "ec" and component:
        name = _normalize_ec_component_alias(component)
        if name and name not in _EC_GAIN_COMPONENT_SKIP:
            return _ec_component_process_gain(
                component=name,
                process_cfg=process_cfg,
                pid_entry=pid_entry,
                phase_key=phase_key,
            )
    return _process_gain(
        kind=kind,
        process_cfg=process_cfg,
        pid_entry=pid_entry,
        phase_key=phase_key,
    )


def _process_gain(
    *,
    kind: str,
    process_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    phase_key: str,
) -> float | None:
    key = {
        "ec": "ec_gain_per_ml",
        "ph_up": "ph_up_gain_per_ml",
        "ph_down": "ph_down_gain_per_ml",
    }.get(kind)
    if key is None:
        return None
    raw = process_cfg.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None

    stats = pid_entry.get("stats") if isinstance(pid_entry.get("stats"), Mapping) else {}
    adaptive = stats.get("adaptive") if isinstance(stats.get("adaptive"), Mapping) else {}
    gains = adaptive.get("gains") if isinstance(adaptive.get("gains"), Mapping) else {}
    learned_entry = gains.get(key) if isinstance(gains.get(key), Mapping) else {}

    try:
        learned_gain = float(learned_entry.get("ema"))
    except (TypeError, ValueError):
        learned_gain = 0.0
    try:
        observations = int(learned_entry.get("observations") or 0)
    except (TypeError, ValueError):
        observations = 0
    if learned_gain <= 0 or observations <= 0:
        return value

    retention_ema = _coerce_ratio(adaptive.get("retention_ema"))
    wave_score_ema = _coerce_ratio(adaptive.get("wave_score_ema"))
    weight = min(1.0, observations / 6.0)
    if retention_ema is not None:
        weight *= max(0.25, retention_ema)
    if wave_score_ema is not None:
        weight *= max(0.35, 1.0 - min(0.65, wave_score_ema))
    effective = value * (1.0 - weight) + learned_gain * weight
    if phase_key == "tank_recirc" and kind == "ec":
        # В recirculation режим должен оставаться консервативным:
        # learned EC gain может повышать уверенность, но не должен уменьшать
        # авторитетный gain из process calibration и раздувать следующий импульс.
        effective = max(value, effective)
    return max(value * 0.25, min(value * 4.0, effective))
