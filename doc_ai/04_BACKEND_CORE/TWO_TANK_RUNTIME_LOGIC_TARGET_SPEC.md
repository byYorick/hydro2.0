# TWO_TANK_RUNTIME_LOGIC_TARGET_SPEC.md
# Целевая спецификация 2-баковой логики (v2 target)

**Версия:** 1.0  
**Дата обновления:** 2026-02-19  
**Статус:** LEGACY TARGET / SUPERSEDED BY AE2-Lite PLAN

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy workflow aliases не поддерживаются.

> Внимание: для текущей реализации использовать
> `doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md`.
> Пункты про `manual_resume` в этом документе считаются историческими.

---

## 1. Цель

Зафиксировать целевой контракт для доработки:
- `automation-engine` (state-machine, retry/recovery, fail-safe);
- `laravel + frontend` (manual resume API и UI-кнопка подтверждения);
- test firmware `irr`-ноды (`state` snapshot + события + interlock).

Документ описывает **to-be** контракт, а не текущий `as-is`.

---

## 2. Зафиксированные параметры

- `irr state` поля — `bool`.
- Ручное подтверждение после автопопыток — обязательно (`manual_resume`).
- Автоповторы recovery — `2`.
- Вторая попытка recovery timeout — `base_timeout * 1.5`.
- Ошибка датчиков — отдельный `error_code` + описание.
- Полив: после `10` безуспешных итераций коррекции — `reason_code`, полив продолжается по расписанию.

---

## 3. Контракт `irr/state` (snapshot)

## 3.1. Семантика

`automation-engine` запрашивает state у `irr`-ноды на critical этапах и сравнивает
фактическое состояние с ожидаемым (expected-vs-actual).

## 3.2. Канонические поля snapshot

```json
{
  "clean_level_max": true,
  "clean_level_min": true,
  "solution_level_max": false,
  "solution_level_min": true,
  "valve_clean_fill": false,
  "valve_clean_supply": true,
  "valve_solution_fill": true,
  "valve_solution_supply": false,
  "valve_irrigation": false,
  "pump_main": true
}
```

## 3.3. Freshness

Snapshot обязан содержать/сопровождаться метаданными свежести:
- `sample_ts` (UTC timestamp);
- `age_sec`;
- `max_age_sec` (runtime-config);
- `is_fresh`.

При `is_fresh=false` поведение fail-closed (`two_tank_level_stale` или профильный код).

## 3.4. Expected-vs-Actual check

На critical этапах сохраняется результат проверки:

```json
{
  "matches": false,
  "mismatches": [
    {
      "field": "valve_solution_fill",
      "expected": true,
      "actual": false,
      "severity": "critical"
    }
  ]
}
```

При `matches=false` и `severity=critical` — stop/fail-safe + событие/алерт.

---

## 4. Контракт ручного подтверждения (`manual_resume`)

## 4.1. Frontend -> Laravel

`POST /api/zones/{zone}/automation/manual-resume`

Request:
```json
{
  "task_id": "st-...",
  "source": "frontend_manual_resume"
}
```

Response (пример):
```json
{
  "status": "ok",
  "data": {
    "zone_id": 12,
    "task_id": "st-...",
    "manual_resume": "accepted"
  }
}
```

## 4.2. Laravel -> Automation-engine (upstream)

`POST /zones/{zone_id}/automation/manual-resume`

Назначение: снять блокировку `manual_ack_required` и возобновить workflow/recovery.

## 4.3. UI поведение

- Если у текущей задачи `reason_code=manual_ack_required_after_retries`, UI обязан показать кнопку подтверждения.
- По клику:
  - отправить `manual_resume`;
  - обновить `scheduler-task` и `automation-state`;
  - показать результат (`accepted/rejected/failed`).

---

## 5. Новые коды ошибок/причин

## 5.1. Error codes

- `sensor_state_inconsistent`  
  Пример: `clean_level_max=true` и `clean_level_min=false`.

## 5.2. Reason codes

- `manual_ack_required_after_retries`
- `irrigation_correction_attempts_exhausted_continue_irrigation`

---

## 6. Целевая state-machine политика

- Recovery policy:
  - attempt #1: `timeout = base_timeout`;
  - attempt #2: `timeout = base_timeout * 1.5`;
  - после исчерпания: `manual_ack_required_after_retries`.
- Полив:
  - до `10` коррекций на цикл;
  - после 10 — reason-code `irrigation_correction_attempts_exhausted_continue_irrigation`;
  - полив не останавливается автоматически по этой причине.

---

## 7. Без legacy-совместимости

- Legacy aliases/stages (`cycle_start`, `refill_check` и т.д.) не поддерживаются в target-контракте.
- Используются только нормализованные workflow-stages целевой 2-баковой логики.

---

## 8. Связанные документы

- `doc_ai/04_BACKEND_CORE/TWO_TANK_RUNTIME_LOGIC_CURRENT.md` (as-is реализация)
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`
