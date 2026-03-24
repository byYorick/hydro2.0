# ARCHITECTURE_FLOWS.md
# Ключевые архитектурные потоки hydro 2.0 (AE3 authority runtime)

**Версия:** 3.3  
**Дата обновления:** 2026-03-24  
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
- `automation-engine` может сделать не более одного transient retry к `history-logger` при transport error / `HTTP 5xx`; дальнейшая деградация — fail-closed.

---

## 3. AE3 запуск цикла

`Laravel scheduler (insert intent) -> POST /zones/{id}/start-cycle -> ZoneRunner`

Правила:
- внешний wake-up endpoint только один: `POST /zones/{id}/start-cycle`;
- scheduler передает намерение через `zone_automation_intents`;
- workflow шаги выполняются последовательно: `send -> await terminal -> next`.
- single-writer на уровне зоны: одновременно допускается только один активный `start-cycle` runner на зону;
- при активном intent/active task endpoint возвращает `409 start_cycle_zone_busy`.

Single-writer policy:
- runtime работает fail-closed: при недоступной проверке writer-state
  continuous loop side-effects блокируются;
- fallback writer-режим не поддерживается.

---

## 4. Feedback и телеметрия для AE3

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

Канонический runtime read-path для automation/runtime-конфига:

- raw authority state хранится в `automation_config_documents`;
- compiler собирает `automation_effective_bundles`;
- AE3 читает bundle по `grow_cycles.settings.bundle_revision`;
- Laravel readiness/start path читает bundle и `automation_config_violations`.

Precedence compile:
`system.* -> zone.* -> cycle.*`

Ограничения:
- runtime path не зависит от `/api/internal/effective-targets/*`;
- runtime path не читает legacy automation config tables как source of truth;
- fallback на чтении не допускается.

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
- `04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md`
- `04_BACKEND_CORE/ae3lite.md`
- `04_BACKEND_CORE/REST_API_REFERENCE.md`
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `04_BACKEND_CORE/ae3lite.md`

---

## 8. AE3 runtime pipeline

Базовый command flow (инвариант не меняется):

`Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`

Режимы выполнения:
- `ae3`: ownership по зоне переключается на current authority runtime через `zones.automation_runtime='ae3'`.

Routing:
- cutover выполняется вручную по зоне через поле `zones.automation_runtime`;
- автоматический canary-router, `ae3l_canary_state` и bridge gate orchestration в canonical AE3 runtime не используются.

Compatibility path:
- ingress до cutover остаётся через `POST /zones/{id}/start-cycle` и `zone_automation_intents`;
- status migration идёт через canonical `GET /internal/tasks/{task_id}`;
- dual-run shadow, legacy status mirrors и `root_intent_id` bridge в canonical v1 не требуются.

AE3 fast-path / fallback:
- terminal transition intent-а публикует `scheduler_intent_terminal`, который будит Laravel listener и AE3 worker fast-path;
- fast-path не заменяет canonical PostgreSQL state и reconcile polling;
- ожидание terminal legacy command status использует bounded backoff, а не фиксированный sleep.

AE3 timeout invariants:
- whole-task execution ограничен `AE_MAX_TASK_EXECUTION_SEC` (default `900s`);
- timeout-path обязан пройти через fail-safe shutdown и terminal `failed`, а не оставлять `ae_tasks`/`zone_automation_intents` в active state;
- scheduler default timing chain: `expires_after_sec = 600s`, effective `hard_stale_after_sec = max(900, expires_after_sec * 2)`; при дефолтном `expires_after_sec` это даёт `1200s`.
