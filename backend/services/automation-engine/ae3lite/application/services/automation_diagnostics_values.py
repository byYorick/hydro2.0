"""Shared immutable values/records for application/services/automation_observability.py."""

from __future__ import annotations

_ACTIVE_TASK_STATUSES = frozenset({"pending", "claimed", "running", "waiting_command"})

_DISPATCH_STUCK_STATUSES = frozenset({"pending", "claimed"})

_SENSOR_BLOCK_REASONS = frozenset(
    {
        "smart_soil_target_missing",
        "smart_soil_telemetry_missing_or_stale",
    }
)

_SOLUTION_TEMP_BLOCK_REASONS = frozenset(
    {
        "solution_temp_out_of_band",
        "solution_temp_unavailable",
    }
)

_HANG_HINT_LABELS: dict[str, str] = {
    "stage_deadline_exceeded": "Превышен дедлайн текущего этапа",
    "waiting_command_stuck": "Задача ждёт ответа по команде дольше ожидаемого",
    "stage_elapsed_long": "Этап выполняется дольше типового времени",
    "workflow_snapshot_stale": "Снимок workflow в БД не обновлялся при активной фазе",
    "no_active_task_during_workflow": "Активная фаза workflow без running-задачи AE3",
    "level_sensors_unlatched": "Датчики уровня не подтверждают заполнение баков",
    "telemetry_unavailable": "Телеметрия зоны недоступна для диагностики",
    "correction_substep_stalled": "Подшаг коррекции pH/EC выполняется слишком долго",
    "nodes_offline": "Обязательные узлы зоны offline или stale",
    "task_dispatch_stuck": "Задача AE3 не переходит в running дольше ожидаемого",
    "level_clean_max_unlatched": "Верхний уровень чистой воды не подтверждён",
    "level_solution_max_unlatched": "Верхний уровень раствора не подтверждён",
    "level_solution_min_unlatched": "Нижний уровень раствора не подтверждён",
    "irrigation_sensor_blocked": "Полив пропущен: нет цели влажности или свежего измерения",
    "solution_temp_blocked": "Полив пропущен: температура раствора вне допуска или датчик недоступен",
}

_HANG_HINT_RECOMMENDATIONS: dict[str, str] = {
    "stage_deadline_exceeded": "Проверьте датчики уровня, узел irrig и последние команды fill/stop.",
    "waiting_command_stuck": "Проверьте MQTT, history-logger и command_response для последней команды.",
    "stage_elapsed_long": "Сверьте уровни баков, online-статус irrig-ноды и журнал zone_events.",
    "workflow_snapshot_stale": "Возможен рестарт AE или зависшая задача — проверьте ae_tasks и логи AE3.",
    "no_active_task_during_workflow": "Запустите start-cycle или проверьте pending intent планировщика.",
    "level_sensors_unlatched": "Перезапустите fill workflow или проверьте физику/симулятор level_switch.",
    "telemetry_unavailable": "Проверьте history-logger и sensors/telemetry_last для зоны.",
    "correction_substep_stalled": "Проверьте pH/EC сенсоры, насосы дозирования и corr_step в ae_tasks.",
    "nodes_offline": "Проверьте питание, Wi‑Fi/MQTT и last_seen_at узлов irrig/ph/ec.",
    "task_dispatch_stuck": "Проверьте lease AE3, очередь claim и логи automation-engine.",
    "level_clean_max_unlatched": "Перезапустите clean fill или проверьте level_clean_max / симулятор.",
    "level_solution_max_unlatched": "Перезапустите solution fill или проверьте level_solution_max.",
    "level_solution_min_unlatched": "Проверьте уровень раствора и гидравлику бака.",
    "irrigation_sensor_blocked": "Проверьте датчик влажности и цель в профиле зоны. Это успешный пропуск, не сбой задачи.",
    "solution_temp_blocked": "Проверьте датчик раствора и пределы фазы. Уже идущая доза не обрывается. Это не сбой задачи.",
}
