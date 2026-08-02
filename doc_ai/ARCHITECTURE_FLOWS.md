# ARCHITECTURE_FLOWS.md
# Ключевые архитектурные потоки hydro 2.0 (AE3 authority runtime)

**Версия:** 3.4  
**Дата обновления:** 2026-08-02  
**Статус:** Актуально

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: HTTP-транспорт задач планировщика удалён из runtime.

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

## 3. AE3 запуск задач (ingress)

`Laravel scheduler (insert intent) -> POST wake-up -> AE3 worker / ZoneRunner`

Канонические внешние ingress (см. `ae3lite.md` / `AGENT.md`):
- `POST /zones/{id}/start-cycle` — diagnostics / cycle_start / compat non-irrigation;
- `POST /zones/{id}/start-irrigation` — штатный полив по расписанию;
- `POST /zones/{id}/start-lighting-tick` — lighting tick для `automation_runtime='ae3'`;
- `POST /zones/{id}/start-solution-topup` — автодолив раствора (`solution_topup`);
- `POST /zones/{id}/start-solution-change` — полуавто смена раствора (`solution_change`);
- `POST /greenhouses/{id}/start-climate-tick` — greenhouse climate tick.

Правила:
- Laravel scheduler-dispatch пишет намерение в `zone_automation_intents` и будит соответствующий ingress;
- workflow шаги: `send -> await terminal (poll commands) -> next`;
- single-writer на уровне зоны: одна активная execution task / lease;
- при busy — `409 start_cycle_zone_busy` (или эквивалентный conflict ingress).

Single-writer policy:
- runtime работает fail-closed: при недоступной проверке writer-state
  continuous loop side-effects блокируются;
- fallback writer-режим не поддерживается.

---

## 4. Feedback и телеметрия для AE3

`PostgreSQL LISTEN/NOTIFY (fast-path) + reconcile polling (SoT)`

Канон подписок AE3 (`PYTHON_SERVICES_ARCH.md`, `ae3lite` `NOTIFY_CHANNELS`):
- `scheduler_intent_terminal` — terminal lifecycle intent → `IntentStatusListener` → `worker.kick()`;
- `ae_zone_event` — node runtime events (`LEVEL_SWITCH_CHANGED`, storage/e-stop, …) после записи HL → `ZoneEventListener` → `worker.kick()`.

AE3 **не** подписан на:
- `ae_command_status` — остаётся для scheduler cockpit / других потребителей; terminal команд AE3 **poll-ит** из `commands` / `ae_commands`;
- `ae_signal_update` — не используется AE3 runtime (historical / reserved).

Правила:
- `NOTIFY` — только fast-path wake-up;
- polling (`commands`, `telemetry_last`, `zone_events`) — обязательный fallback; DB = source of truth;
- stale critical signals → fail-closed + `zone_events`.

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
- runtime path не читает устаревшие automation config tables как source of truth;
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

---

## 8. AE3 runtime pipeline

Базовый command flow (инвариант не меняется):

`Laravel scheduler-dispatch -> Automation-Engine -> history-logger -> MQTT -> ESP32`

Режимы выполнения:
- `ae3`: ownership по зоне переключается на current authority runtime через `zones.automation_runtime='ae3'`.

Routing:
- cutover выполняется вручную по зоне через поле `zones.automation_runtime`;
- автоматический canary-router, `ae3l_canary_state` и bridge gate orchestration в canonical AE3 runtime не используются.

Compatibility path:
- zone ingress — через `start-cycle` / `start-irrigation` / `start-lighting-tick` / `start-solution-topup` / `start-solution-change` + `zone_automation_intents`;
- greenhouse climate — `start-climate-tick`;
- status — canonical `GET /internal/tasks/{task_id}`;
- dual-run shadow, зеркала статусов вне канона и `root_intent_id` bridge в canonical v1 не требуются.

AE3 fast-path / fallback:
- `scheduler_intent_terminal` и `ae_zone_event` будят AE3 worker (`worker.kick()`);
- terminal статусы команд AE3 получает polling'ом (не через `ae_command_status`);
- fast-path не заменяет canonical PostgreSQL state и reconcile polling;
- ожидание terminal в `commands` — bounded backoff, не фиксированный sleep.

AE3 timeout invariants:
- whole-task execution ограничен `AE_MAX_TASK_EXECUTION_SEC` (default `900s`);
- timeout-path обязан пройти через fail-safe shutdown и terminal `failed`, а не оставлять `ae_tasks`/`zone_automation_intents` в active state;
- scheduler default timing chain: `expires_after_sec = 600s`, effective `hard_stale_after_sec = max(900, expires_after_sec * 2)`; при дефолтном `expires_after_sec` это даёт `1200s`.
