# ARCHITECTURE_FLOWS.md
# Ключевые архитектурные потоки hydro 2.0 (AE 1.0.0)

**Версия:** 3.5  
**Дата обновления:** 2026-09-25  
**Статус:** Актуально

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: диспетчер Laravel и ingress `start-*` зон удалены; wake-up — тик воркера 1.0.0.

---

## 1. Защищённый pipeline телеметрии

`ESP32 -> MQTT -> history-logger -> PostgreSQL -> Laravel -> Vue/Android`

Инварианты:
- `history-logger` пишет `telemetry_samples` и `telemetry_last`;
- изменение транспортного контракта требует синхронного обновления `doc_ai/03_TRANSPORT_MQTT/*`.

---

## 2. Защищённый pipeline команд

`Automation-Engine (тик AE 1.0.0) -> history-logger -> MQTT -> ESP32`

Инварианты:
- прямой MQTT publish из Laravel/automation-engine запрещён;
- единственная точка публикации команд: `POST /commands` в `history-logger`.
- `automation-engine` может сделать не более одного transient retry к `history-logger` при transport error / `HTTP 5xx`; дальнейшая деградация — fail-closed.
- диспетчера Laravel (`automation:dispatch-schedules`, `ScheduleDispatcher`) нет.

---

## 3. AE 1.0.0 пробуждение и HTTP

`Тик воркера ae4 → due_at=now (мутация зоны) + один POST /greenhouses/{id}/start-climate-tick на теплицу`

Канон поведения — `ae4.md` / `AGENT.md`. Живой HTTP automation-engine:
- `/health`, `/metrics`, состояние зоны, control-mode;
- `POST /greenhouses/{id}/start-climate-tick` — единственный climate-tick на теплицу из тика воркера.

Маршрутов `start-irrigation`, `start-lighting-tick`, `start-solution-topup`, `start-cycle`, `start-solution-change` нет.

Правила:
- единственное автоматическое пробуждение зон — тик воркера 1.0.0;
- single-writer на уровне зоны: одна активная execution task / lease;
- OFF света и закрытие тракта — класс безопасности, мутацию воды/химии не занимают.

Single-writer policy:
- runtime работает fail-closed: при недоступной проверке writer-state
  continuous loop side-effects блокируются;
- fallback writer-режим не поддерживается.

---

## 4. Feedback и телеметрия для AE 1.0.0

`PostgreSQL reconcile polling (SoT) + опциональный LISTEN/NOTIFY (fast-path)`

Terminal команд runtime **poll-ит** из `commands` / `ae_commands`. DB = source of truth.

Правила:
- polling (`commands`, `telemetry_last`, `zone_events`) — обязательный fallback;
- stale critical signals → fail-closed + `zone_events`.

---

## 5. Runtime read-model

`automation-engine -> PostgreSQL (direct SQL read-model)`

Канонический runtime read-path для automation/runtime-конфига:

- raw authority state хранится в `automation_config_documents`;
- compiler собирает `automation_effective_bundles`;
- AE 1.0.0 читает bundle по `grow_cycles.settings.bundle_revision`;
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
- `04_BACKEND_CORE/ae4.md`
- `04_BACKEND_CORE/REST_API_REFERENCE.md`
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

---

## 8. AE 1.0.0 runtime pipeline

Базовый command flow:

`Automation-Engine (тик 1.0.0) -> history-logger -> MQTT -> ESP32`

Runtime:
- воркер обслуживает зоны с `automation_runtime IS DISTINCT FROM 'ae3'`;
- значение `ae3` историческое и не обслуживается; пакета `ae3lite` нет.

Routing:
- смена `zones.automation_runtime` при active task/lease запрещена;
- автоматический canary-router и bridge gate orchestration не используются.

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
