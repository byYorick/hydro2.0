"""Разрешение одного импульса дозы. Публикация cmd=dose — не здесь."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from ae4.domain.planting import TelemetrySample
from ae4.domain.sensor_gate import is_fresh, sample_in_bounds

ObservationOutcome = Literal["effect", "no_effect", "sensor_stale", "pending"]
Reagent = Literal["ph_up", "ph_down", "nutrition"]

_DEFAULT_NO_EFFECT_LIMIT = 3


@dataclass(frozen=True)
class DoseDecision:
    allow_pulse: bool
    dose_ml: float | None
    reagent: str | None
    reason_code: str
    human_message: str
    blocks_shot: bool
    critical_alert: bool = False


@dataclass(frozen=True)
class DoseReagentState:
    """Состояние реагента между тиками (last_dose_at только после DONE)."""

    reagent: str
    last_dose_at: datetime | None
    no_effect_count: int
    baseline_value: float | None
    last_dose_ml: float | None
    observation: ObservationOutcome


@dataclass(frozen=True)
class ControllerDoseParams:
    gain: float | None
    max_dose_ml: float | None
    min_interval_sec: int | None
    decision_window_sec: int | None
    min_effect_fraction: float | None
    no_effect_limit: int | None
    min_dose_ms: int | None
    ml_per_sec: float | None


def dose_ml_for_error(
    *,
    error_to_target: float,
    gain: float,
    max_dose_ml: float,
) -> float:
    """Один импульс: |ошибка|/gain, не выше max_dose_ml контроллера."""
    if gain <= 0:
        raise ValueError("gain контроллера должен быть > 0")
    if max_dose_ml <= 0:
        raise ValueError("max_dose_ml контроллера должен быть > 0")
    raw = abs(error_to_target) / gain
    return min(raw, max_dose_ml)


def duration_ms_for_dose_ml(*, dose_ml: float, ml_per_sec: float) -> int:
    """Только для порога min_dose_ms. В команду узла длительность не кладётся."""
    if ml_per_sec <= 0 or dose_ml <= 0:
        return 0
    return int(dose_ml / ml_per_sec * 1000)


def below_min_dose_ms(
    *,
    dose_ml: float,
    min_dose_ms: int | None,
    ml_per_sec: float | None,
) -> bool:
    """Импульс ниже уже существующего min_dose_ms не публикуется."""
    if min_dose_ms is None or min_dose_ms <= 0:
        return False
    if ml_per_sec is None or ml_per_sec <= 0:
        # Есть порог, но нет калибровки для сверки — импульса нет.
        return True
    return duration_ms_for_dose_ml(dose_ml=dose_ml, ml_per_sec=ml_per_sec) < int(min_dose_ms)


def evaluate_ph_pulse(
    *,
    ph_sample: TelemetrySample | None,
    ph_target: float | None,
    ph_unit: str | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
    gain: float | None = None,
    max_dose_ml: float | None = None,
    ph_up_gain: float | None = None,
    ph_down_gain: float | None = None,
) -> DoseDecision:
    """pH ниже цели — ph_up, выше — ph_down. Протухший pH импульс запрещает, кадр не запрещает."""
    if ph_target is None:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_target_absent",
            human_message="Цели pH нет — импульс кислоты или щёлочи не нужен",
            blocks_shot=False,
        )
    if not is_fresh(sample=ph_sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_stale",
            human_message="pH протух — импульса нет, кадр этим фактом не запрещён",
            blocks_shot=False,
        )
    assert ph_sample is not None
    if not sample_in_bounds(sample=ph_sample):
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_out_of_bounds",
            human_message="pH вне 0–14 — как норму не обновляем, импульса нет",
            blocks_shot=False,
        )
    if ph_unit is not None and ph_sample.unit is not None and ph_unit != ph_sample.unit:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_unit_mismatch",
            human_message="Единицы pH канала и цели не совпадают — импульса нет",
            blocks_shot=False,
        )
    error = ph_sample.value - ph_target
    if error == 0:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_on_target",
            human_message="pH на цели — импульса нет",
            blocks_shot=False,
        )
    reagent = "ph_down" if error > 0 else "ph_up"
    # Два реагента — два gain. Одиночный gain оставлен для тестов волны 1.
    if reagent == "ph_up":
        resolved_gain = ph_up_gain if ph_up_gain is not None else gain
    else:
        resolved_gain = ph_down_gain if ph_down_gain is not None else gain
    if resolved_gain is None or resolved_gain <= 0 or max_dose_ml is None or max_dose_ml <= 0:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ph_controller_incomplete",
            human_message="Нет gain или max_dose_ml контроллера pH — импульса нет",
            blocks_shot=False,
        )
    ml = dose_ml_for_error(
        error_to_target=error,
        gain=resolved_gain,
        max_dose_ml=max_dose_ml,
    )
    return DoseDecision(
        allow_pulse=True,
        dose_ml=ml,
        reagent=reagent,
        reason_code="ph_pulse",
        human_message=f"Импульс {reagent}: {ml:.4f} мл",
        blocks_shot=False,
    )


def evaluate_ec_pulse(
    *,
    ec_sample: TelemetrySample | None,
    ec_target: float | None,
    ec_unit: str | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
    stale_ec_allows_shot: bool | None,
    gain: float | None = None,
    max_dose_ml: float | None = None,
    ec_drain_sample: TelemetrySample | None = None,
    ec_max: float | None = None,
) -> DoseDecision:
    """
    Протухший EC: пустая настройка кадр запрещает; явное «разрешить» кадр этим фактом
    не запрещает, импульса нет.
    Свежий EC стока выше коридора — соли нет даже если feed ниже цели.
    """
    if not is_fresh(sample=ec_sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        # Нет цели EC — зона не держит соль; кадр этим фактом не запрещаем.
        if ec_target is None:
            return DoseDecision(
                allow_pulse=False,
                dose_ml=None,
                reagent=None,
                reason_code="ec_stale_no_target",
                human_message="EC протух, цели нет — импульса нет, кадр этим фактом не запрещён",
                blocks_shot=False,
            )
        if stale_ec_allows_shot is True:
            return DoseDecision(
                allow_pulse=False,
                dose_ml=None,
                reagent=None,
                reason_code="ec_stale_shot_allowed",
                human_message="EC протух — импульса нет, кадр настройкой разрешён",
                blocks_shot=False,
            )
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_stale_shot_blocked",
            human_message="EC протух — кадр запрещён (пустая или запрещающая настройка)",
            blocks_shot=True,
        )
    assert ec_sample is not None
    if not sample_in_bounds(sample=ec_sample):
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_out_of_bounds",
            human_message="EC вне 0–20 — как норму не обновляем, импульса нет",
            blocks_shot=False,
        )
    if ec_target is None:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_target_absent",
            human_message="Цели EC нет — импульса соли нет",
            blocks_shot=False,
        )
    if ec_unit is not None and ec_sample.unit is not None and ec_unit != ec_sample.unit:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_unit_mismatch",
            human_message="Единицы EC канала и цели не совпадают — импульса нет",
            blocks_shot=False,
        )
    drain_block = drain_ec_blocks_nutrition(
        ec_drain_sample=ec_drain_sample,
        ec_max=ec_max,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
        ec_unit=ec_unit,
    )
    if drain_block is not None:
        return drain_block
    if gain is None or gain <= 0 or max_dose_ml is None or max_dose_ml <= 0:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_controller_incomplete",
            human_message="Нет gain или max_dose_ml контроллера EC — импульса нет",
            blocks_shot=False,
        )
    error = ec_target - ec_sample.value
    if error <= 0:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_not_below_target",
            human_message="EC не ниже цели — импульса соли нет",
            blocks_shot=False,
        )
    ml = dose_ml_for_error(error_to_target=error, gain=gain, max_dose_ml=max_dose_ml)
    return DoseDecision(
        allow_pulse=True,
        dose_ml=ml,
        reagent="nutrition",
        reason_code="ec_pulse",
        human_message=f"Импульс соли: {ml:.4f} мл",
        blocks_shot=False,
    )


def drain_ec_blocks_nutrition(
    *,
    ec_drain_sample: TelemetrySample | None,
    ec_max: float | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
    ec_unit: str | None,
) -> DoseDecision | None:
    """Высокий свежий EC стока запрещает соль. Разбавление feed к этому каналу не привязано."""
    if ec_drain_sample is None or ec_max is None:
        return None
    if not is_fresh(
        sample=ec_drain_sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec
    ):
        return None
    if (
        ec_unit is not None
        and ec_drain_sample.unit is not None
        and ec_unit != ec_drain_sample.unit
    ):
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=None,
            reason_code="ec_drain_unit_mismatch",
            human_message="Единицы EC стока и цели не совпадают — импульса соли нет",
            blocks_shot=False,
        )
    if not sample_in_bounds(sample=ec_drain_sample):
        return None
    if float(ec_drain_sample.value) <= float(ec_max):
        return None
    return DoseDecision(
        allow_pulse=False,
        dose_ml=None,
        reagent=None,
        reason_code="ec_drain_above_corridor",
        human_message="EC стока выше коридора — соли нет",
        blocks_shot=False,
    )


def resolve_observation(
    *,
    state: DoseReagentState,
    now: datetime,
    sample: TelemetrySample | None,
    telemetry_max_age_sec: int | None,
    decision_window_sec: int | None,
    gain: float | None,
    min_effect_fraction: float | None,
) -> DoseReagentState:
    """Окно наблюдения: эффект / нет эффекта / датчик протух. Иначе pending."""
    if state.observation != "pending" or state.last_dose_at is None:
        return state
    if not is_fresh(sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        return DoseReagentState(
            reagent=state.reagent,
            last_dose_at=state.last_dose_at,
            no_effect_count=state.no_effect_count,
            baseline_value=state.baseline_value,
            last_dose_ml=state.last_dose_ml,
            observation="sensor_stale",
        )
    window_sec = int(decision_window_sec or 0)
    if window_sec <= 0:
        return state
    last = _as_naive(state.last_dose_at)
    now_naive = _as_naive(now)
    if now_naive < last + timedelta(seconds=window_sec):
        return state
    assert sample is not None
    if state.baseline_value is None or state.last_dose_ml is None:
        return DoseReagentState(
            reagent=state.reagent,
            last_dose_at=state.last_dose_at,
            no_effect_count=state.no_effect_count,
            baseline_value=state.baseline_value,
            last_dose_ml=state.last_dose_ml,
            observation="sensor_stale",
        )
    if gain is None or gain <= 0 or min_effect_fraction is None or min_effect_fraction <= 0:
        # Нет порога эффекта — окно закрываем как sensor_stale, не считаем no-effect.
        return DoseReagentState(
            reagent=state.reagent,
            last_dose_at=state.last_dose_at,
            no_effect_count=state.no_effect_count,
            baseline_value=state.baseline_value,
            last_dose_ml=state.last_dose_ml,
            observation="sensor_stale",
        )
    expected = abs(float(state.last_dose_ml) * float(gain))
    threshold = expected * float(min_effect_fraction)
    delta = _directional_delta(
        reagent=state.reagent,
        baseline=float(state.baseline_value),
        current=float(sample.value),
    )
    is_no_effect = delta < threshold
    next_count = state.no_effect_count + 1 if is_no_effect else 0
    return DoseReagentState(
        reagent=state.reagent,
        last_dose_at=state.last_dose_at,
        no_effect_count=next_count,
        baseline_value=state.baseline_value,
        last_dose_ml=state.last_dose_ml,
        observation="no_effect" if is_no_effect else "effect",
    )


def reagent_pulse_blocked_by_state(
    *,
    state: DoseReagentState | None,
    now: datetime,
    min_interval_sec: int | None,
    no_effect_limit: int | None,
) -> DoseDecision | None:
    """Возвращает запрет, если реагент остановлен или окно/интервал не прошли."""
    if state is None:
        return None
    limit = int(no_effect_limit) if no_effect_limit and no_effect_limit > 0 else _DEFAULT_NO_EFFECT_LIMIT
    if state.no_effect_count >= limit:
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=state.reagent,
            reason_code="reagent_no_effect_stopped",
            human_message=(
                f"Реагент {state.reagent}: три подряд no-effect — импульс остановлен"
            ),
            blocks_shot=False,
            critical_alert=True,
        )
    if state.last_dose_at is None:
        return None
    interval = int(min_interval_sec or 0)
    if interval > 0:
        last = _as_naive(state.last_dose_at)
        now_naive = _as_naive(now)
        if now_naive < last + timedelta(seconds=interval):
            return DoseDecision(
                allow_pulse=False,
                dose_ml=None,
                reagent=state.reagent,
                reason_code="reagent_min_interval",
                human_message=f"Реагент {state.reagent}: ждём min_interval",
                blocks_shot=False,
            )
    if state.observation == "pending":
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=state.reagent,
            reason_code="reagent_observation_pending",
            human_message=f"Реагент {state.reagent}: окно наблюдения ещё не закрыто",
            blocks_shot=False,
        )
    return None


def evaluate_tick_dose(
    *,
    ec_sample: TelemetrySample | None,
    ph_sample: TelemetrySample | None,
    ec_target: float | None,
    ph_target: float | None,
    ec_unit: str | None,
    ph_unit: str | None,
    ec_params: ControllerDoseParams,
    ph_params: ControllerDoseParams,
    now: datetime,
    telemetry_max_age_sec: int | None,
    stale_ec_allows_shot: bool | None,
    ec_state: DoseReagentState | None = None,
    ph_up_state: DoseReagentState | None = None,
    ph_down_state: DoseReagentState | None = None,
    ph_up_gain: float | None = None,
    ph_down_gain: float | None = None,
    ec_drain_sample: TelemetrySample | None = None,
    ec_max: float | None = None,
) -> DoseDecision:
    """
    Один импульс за тик: сначала соль (nutrition), иначе pH-up/pH-down.
    Питание раньше кислотности (§2.4 NEED_ORDER).
    """
    ec = evaluate_ec_pulse(
        ec_sample=ec_sample,
        ec_target=ec_target,
        ec_unit=ec_unit,
        gain=ec_params.gain,
        max_dose_ml=ec_params.max_dose_ml,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
        stale_ec_allows_shot=stale_ec_allows_shot,
        ec_drain_sample=ec_drain_sample,
        ec_max=ec_max,
    )
    if ec.blocks_shot:
        return ec
    if ec.reason_code == "ec_drain_above_corridor":
        return ec
    # Соль выше кислоты: если EC ниже цели — только nutrition в этом тике (или её гейт).
    if ec.allow_pulse and ec.dose_ml is not None:
        return _gate_allowed_pulse(
            candidate=ec,
            state=ec_state,
            now=now,
            params=ec_params,
        )

    ph = evaluate_ph_pulse(
        ph_sample=ph_sample,
        ph_target=ph_target,
        ph_unit=ph_unit,
        gain=ph_params.gain,
        max_dose_ml=ph_params.max_dose_ml,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
        ph_up_gain=ph_up_gain,
        ph_down_gain=ph_down_gain,
    )
    if not ph.allow_pulse or ph.dose_ml is None or ph.reagent is None:
        return ph if ph.reason_code != "ph_target_absent" else ec

    state = ph_up_state if ph.reagent == "ph_up" else ph_down_state
    return _gate_allowed_pulse(candidate=ph, state=state, now=now, params=ph_params)


def _gate_allowed_pulse(
    *,
    candidate: DoseDecision,
    state: DoseReagentState | None,
    now: datetime,
    params: ControllerDoseParams,
) -> DoseDecision:
    blocked = reagent_pulse_blocked_by_state(
        state=state,
        now=now,
        min_interval_sec=params.min_interval_sec,
        no_effect_limit=params.no_effect_limit,
    )
    if blocked is not None:
        return blocked
    assert candidate.dose_ml is not None
    if below_min_dose_ms(
        dose_ml=float(candidate.dose_ml),
        min_dose_ms=params.min_dose_ms,
        ml_per_sec=params.ml_per_sec,
    ):
        return DoseDecision(
            allow_pulse=False,
            dose_ml=None,
            reagent=candidate.reagent,
            reason_code="below_min_dose_ms",
            human_message="Импульс ниже min_dose_ms — не публикуется",
            blocks_shot=False,
        )
    return candidate


def _directional_delta(*, reagent: str, baseline: float, current: float) -> float:
    if reagent == "ph_down":
        return baseline - current
    # ph_up и nutrition — рост величины к цели.
    return current - baseline


def _as_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


__all__ = [
    "DoseDecision",
    "DoseReagentState",
    "ControllerDoseParams",
    "ObservationOutcome",
    "dose_ml_for_error",
    "duration_ms_for_dose_ml",
    "below_min_dose_ms",
    "evaluate_ph_pulse",
    "evaluate_ec_pulse",
    "drain_ec_blocks_nutrition",
    "resolve_observation",
    "reagent_pulse_blocked_by_state",
    "evaluate_tick_dose",
]
