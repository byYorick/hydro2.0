# DISASTER_RECOVERY_CHARTER.md
# Паспорт pipeline: offline-режимы, local fallback, resilience

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/DISASTER_RECOVERY_CHARTER.md`
**Связанные:** `firmware/`, `WATER_FLOW_ENGINE.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`

---

## 1. Назначение

Закрытая теплица с клубникой умирает быстро: при обрыве управления полив
не работает → гибель за 4–8 часов жарким днём. Этот pipeline — план на
«что угодно может сломаться в цепочке backend → MQTT → нода» и какая
минимальная функциональность работает без внешних зависимостей.

## 2. Цели

- Узел ESP32 обязан иметь локальный fallback plan полива (по таймеру),
  который активируется при N минут без команд от backend.
- БД может умереть на 4 часа без потери данных (узлы буферизуют).
- Основные сафети-контуры работают без ML / vision / weather — от rule-based
  layer 1 (из `IRRIGATION_ML_PIPELINE §4.1`).
- Recovery после восстановления: резинхронизация без дублирования /
  пропусков.

## 3. Ключевые дизайн-решения

1. **Узел — автономная safety-единица**: на нём есть embedded schedule и
   sensor thresholds. При offline ≥ `BACKEND_TIMEOUT` переходит на
   emergency schedule.
2. **Store-and-forward**: узел буферизует телеметрию локально (NOR-flash)
   при MQTT-недоступности. При восстановлении — отдаёт с timestamp'ами.
3. **Idempotency keys**: все команды из backend имеют cmd_id; узел
   игнорирует дубликаты.
4. **Graceful degradation**: при выключении любого сервиса — остальные
   работают с пометкой «degraded mode».
5. **Runbooks для каждого типа отказа**: в `doc_ai/08_SECURITY_AND_OPS/`
   прописаны пошаговые инструкции.

## 4. Уровни отказов

| Уровень | Что сломалось | Сколько работает | Что нужно делать |
|---|---|---|---|
| L1 | Один ML-сервис | Индефинитно (Layer 2 ET работает) | Investigation, не срочно |
| L2 | Internet / weather API | 24+ часа (работа на локальных данных) | Мониторить, восстановить |
| L3 | Backend Laravel | 2–4 часа (узлы с буферизацией + embedded schedule) | Immediate fix |
| L4 | БД PostgreSQL | 1–2 часа (buffer на узлах) | Immediate fix |
| L5 | MQTT broker | 1–2 часа | Immediate fix |
| L6 | Узел сам сломался | 0 (критично) | Hot-swap + manual override |

## 5. Структура данных

```sql
CREATE TABLE node_fallback_schedules (
  id bigserial PRIMARY KEY,
  node_id bigint NOT NULL REFERENCES nodes(id),
  zone_id bigint NOT NULL REFERENCES zones(id),
  fallback_type varchar(32) NOT NULL,    -- 'irrigation_interval'|'hvac_setpoint'|...
  schedule_json jsonb NOT NULL,          -- часовые интервалы / setpoints
  activates_after_backend_offline_sec integer NOT NULL,
  last_synced_at timestamptz NOT NULL,
  synced_by_node_fw_version varchar(32),
  checksum varchar(64)
);

CREATE TABLE node_buffered_telemetry_status (
  node_id bigint PRIMARY KEY REFERENCES nodes(id),
  oldest_buffered_ts timestamptz,
  buffered_points_count integer,
  last_sync_attempt timestamptz,
  last_successful_sync timestamptz,
  buffer_capacity_bytes integer,
  buffer_used_bytes integer
);

CREATE TABLE dr_drills (
  id bigserial PRIMARY KEY,
  scenario varchar(64) NOT NULL,         -- 'backend_down'|'db_down'|'mqtt_down'|...
  performed_at timestamptz NOT NULL,
  performed_by bigint REFERENCES users(id),
  duration_sec integer,
  outcome varchar(16),                   -- 'pass'|'fail'|'partial'
  notes text,
  runbook_version varchar(32)
);
```

## 6. Firmware требования

- Каждая нода должна иметь persisted `fallback_schedule` (обновляется с
  backend раз в час, хранится в flash).
- При `time_since_last_cmd > BACKEND_TIMEOUT (default 900 сек)` — активация
  fallback mode.
- `fallback mode` выполняет минимальный safety-план: полив по таймеру,
  HVAC в последних known-good setpoints, alerts на buzzer / LED.
- Логирование всех fallback-решений в локальный буфер → backend по
  восстановлении.

## 7. Фазы

| Phase | Задача | DoD |
|---|---|---|
| DR0 | Inventory: какие отказы реалистичны в вашей инфраструктуре | Отчёт |
| DR1 | `node_fallback_schedules` + firmware расширение | Нода выполняет fallback после 15 мин offline |
| DR2 | Store-and-forward буферизация на ноде | Тест: backend down 1 час → данные не потеряны |
| DR3 | Idempotency validation | Повторная команда с тем же cmd_id не исполняется дважды |
| DR4 | Runbook'и для каждого L1–L6 | В `doc_ai/08_` лежат |
| DR5 | DR-drills по расписанию | Ежеквартально симулируем 1 уровень отказа |

## 8. Интеграция

- **Все pipeline'ы** обязаны работать с `degraded_mode` — если часть
  источников данных недоступна, использовать fallback значения и
  помечать advisory как `degraded`.
- **UNIFIED_ALERTING** — `L3-L6 detected` → emergency alert.
- **SENSOR_HEALTH** — помогает определить «железо сломалось» vs «сервис
  сломался».

## 9. Правила для ИИ-агентов

### Можно:
- Добавлять новые DR scenarios в `dr_drills`.
- Улучшать fallback-логику в firmware (с backward compatibility).

### Нельзя:
- Удалять или уменьшать fallback-schedules без ops-approval.
- Тестировать DR на проде без явного окна maintenance (риск живым растениям).
- Deploy firmware без fallback capability.

## 10. Открытые вопросы

1. Буфер на ноде: сколько часов телеметрии должен держать? (≥ 4 ч рекомендуется)
2. Authentication fallback: что, если ноды не могут получить токены — как
   они друг другу доверяют в MQTT?
3. Multi-backend (geo-redundant) — нужен ли на этапе 1 теплицы?

---

# Конец DISASTER_RECOVERY_CHARTER.md
