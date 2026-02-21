# ARCHITECTURE_FLOWS.md
# Ключевые архитектурные потоки hydro 2.0 (AE2-Lite)

**Версия:** 3.0  
**Дата обновления:** 2026-02-21  
**Статус:** Актуально

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy scheduler-task transport удален из runtime.

---

## 1. Защищённый pipeline телеметрии

`ESP32 -> MQTT -> history-logger -> PostgreSQL -> Laravel -> Vue/Android`

Инварианты:
- `history-logger` пишет `telemetry_samples` и `telemetry_last`;
- изменение транспортного контракта требует синхронного обновления `doc_ai/03_TRANSPORT_MQTT/*`.

---

## 2. Защищённый pipeline команд

`Laravel scheduler -> automation-engine -> history-logger -> MQTT -> ESP32`

Инварианты:
- прямой MQTT publish из Laravel/automation-engine запрещён;
- единственная точка публикации команд: `POST /commands` в `history-logger`.

---

## 3. AE2-Lite запуск цикла

`Laravel scheduler (insert intent) -> POST /zones/{id}/start-cycle -> ZoneRunner`

Правила:
- внешний wake-up endpoint только один: `POST /zones/{id}/start-cycle`;
- scheduler передает намерение через `zone_automation_intents`;
- workflow шаги выполняются последовательно: `send -> await terminal -> next`.

---

## 4. Feedback и телеметрия для AE2-Lite

`PostgreSQL LISTEN/NOTIFY + reconcile polling`

Каналы:
- `ae_command_status`
- `ae_signal_update`

Правила:
- `NOTIFY` — fast-path;
- polling — обязательный fallback;
- stale critical signals -> fail-closed + `zone_events`.

---

## 5. Runtime read-model

`automation-engine -> PostgreSQL (direct SQL read-model)`

Приоритет резолва runtime targets/config:
`phase snapshot -> grow_cycle_overrides -> zone_automation_logic_profiles(active mode)`

Ограничение:
- runtime path не зависит от `/api/internal/effective-targets/*`.

---

## 6. Режимы и управление

Поддерживаемые режимы:
- `auto`
- `semi`
- `manual`

API:
- `GET /zones/{id}/state`
- `POST /zones/{id}/control-mode`
- `POST /zones/{id}/manual-step`

---

## 7. Связанные документы

- `SYSTEM_ARCH_FULL.md`
- `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `04_BACKEND_CORE/REST_API_REFERENCE.md`
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md`
