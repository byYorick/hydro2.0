"""Готовность уйти на неделю §11.7. Флаг не гасит тик."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnattendedBlocker:
    reason_code: str
    human_message: str


@dataclass(frozen=True)
class UnattendedFacts:
    """Факты для чистой оценки; сбор из БД — снаружи."""

    planting_active: bool
    control_mode: str
    stale_ec_allows_shot: bool | None
    nutrient_solution_volume_l: float | None
    ec_clean: float | None
    has_clean_fill_binding: bool
    has_feed_topup_binding: bool
    has_frame_with_duration_ms: bool
    has_level_feed: bool
    has_level_clean: bool
    phase_has_ec_target: bool
    has_drain_path: bool
    solution_temp_norm_present: bool
    heater_channel_bound: bool
    co2_norm_present: bool
    co2_channel_bound: bool
    mist_norm_present: bool
    mist_channel_bound: bool
    light_no_guaranteed_off: bool
    telegram_test_ok: bool
    obs_alive: bool
    has_open_task_or_lease: bool


@dataclass(frozen=True)
class UnattendedAssessment:
    ready: bool
    blockers: tuple[UnattendedBlocker, ...]


def evaluate_unattended(facts: UnattendedFacts) -> UnattendedAssessment:
    """Пустой список блокеров → ready. Тик от этого не останавливается."""
    blockers: list[UnattendedBlocker] = []

    if not facts.planting_active:
        blockers.append(
            UnattendedBlocker(
                reason_code="planting_not_active",
                human_message="Нет активной посадки — уйти нельзя",
            )
        )
    mode = str(facts.control_mode or "").strip().lower()
    if mode == "manual":
        blockers.append(
            UnattendedBlocker(
                reason_code="control_mode_manual",
                human_message="Ручной режим — уйти нельзя",
            )
        )

    if facts.stale_ec_allows_shot is None:
        blockers.append(
            UnattendedBlocker(
                reason_code="stale_ec_setting_empty",
                human_message="Не задано правило кадра при протухшем EC",
            )
        )

    if facts.nutrient_solution_volume_l is None or facts.nutrient_solution_volume_l <= 0:
        blockers.append(
            UnattendedBlocker(
                reason_code="tank_volume_missing",
                human_message="Нет объёма бака в фазе посадки",
            )
        )
    if facts.ec_clean is None:
        blockers.append(
            UnattendedBlocker(
                reason_code="ec_clean_missing",
                human_message="Не задан EC чистой воды",
            )
        )

    if not facts.has_clean_fill_binding:
        blockers.append(
            UnattendedBlocker(
                reason_code="clean_fill_binding_missing",
                human_message="Нет привязки набора бака чистой воды",
            )
        )
    if not facts.has_feed_topup_binding:
        blockers.append(
            UnattendedBlocker(
                reason_code="feed_topup_binding_missing",
                human_message="Нет привязки долива рабочего бака",
            )
        )
    if not facts.has_frame_with_duration_ms:
        blockers.append(
            UnattendedBlocker(
                reason_code="frame_duration_missing",
                human_message="Нет кадра полива с длительностью",
            )
        )
    if not facts.has_level_feed:
        blockers.append(
            UnattendedBlocker(
                reason_code="level_feed_unbound",
                human_message="Нет привязки уровней рабочего бака",
            )
        )
    if not facts.has_level_clean:
        blockers.append(
            UnattendedBlocker(
                reason_code="level_clean_unbound",
                human_message="Нет привязки уровней бака чистой воды",
            )
        )

    if facts.phase_has_ec_target and not facts.has_drain_path:
        blockers.append(
            UnattendedBlocker(
                reason_code="drain_path_missing",
                human_message="Фаза умеет EC, но нет пути слива доли в сток",
            )
        )

    if facts.solution_temp_norm_present and not facts.heater_channel_bound:
        blockers.append(
            UnattendedBlocker(
                reason_code="heater_channel_missing",
                human_message="Есть норма температуры раствора, канала нагрева нет",
            )
        )
    if facts.co2_norm_present and not facts.co2_channel_bound:
        blockers.append(
            UnattendedBlocker(
                reason_code="co2_channel_missing",
                human_message="Есть норма CO₂, канала нет",
            )
        )
    if facts.mist_norm_present and not facts.mist_channel_bound:
        blockers.append(
            UnattendedBlocker(
                reason_code="mist_channel_missing",
                human_message="Есть норма тумана, канала нет",
            )
        )

    if facts.light_no_guaranteed_off:
        blockers.append(
            UnattendedBlocker(
                reason_code="light_no_guaranteed_off",
                human_message="Канал света не умеет гарантированно погаснуть",
            )
        )

    if not facts.telegram_test_ok:
        blockers.append(
            UnattendedBlocker(
                reason_code="telegram_not_verified",
                human_message="Telegram не проверен командой alerts:telegram-test",
            )
        )

    if not facts.obs_alive:
        blockers.append(
            UnattendedBlocker(
                reason_code="obs_probe_silent",
                human_message="Профиль наблюдения не поднят или probe процессов молчит",
            )
        )

    if facts.has_open_task_or_lease:
        blockers.append(
            UnattendedBlocker(
                reason_code="open_task_or_lease",
                human_message="Открыта задача или lease зоны",
            )
        )

    return UnattendedAssessment(ready=len(blockers) == 0, blockers=tuple(blockers))


__all__ = [
    "UnattendedAssessment",
    "UnattendedBlocker",
    "UnattendedFacts",
    "evaluate_unattended",
]
