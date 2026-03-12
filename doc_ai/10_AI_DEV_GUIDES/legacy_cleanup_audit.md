# legacy_cleanup_audit.md
# AE2-Lite Legacy Cleanup Audit

**Дата:** 2026-02-22  
**Статус:** Stage 7 completed

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Что удалено из runtime

- legacy scheduler transport:
  - `POST /scheduler/task`
  - `GET /scheduler/task/{task_id}`
- scheduler bootstrap/cutover/internal enqueue runtime endpoints.
- manual resume runtime endpoint:
  - `POST /zones/{id}/automation/manual-resume`
- legacy aliases runtime endpoints:
  - `/zones/{id}/automation-state`
  - `/zones/{id}/automation/control-mode`
  - `/zones/{id}/automation/manual-step`
- legacy compatibility runtime package:
  - `backend/services/automation-engine/legacy/*` (полностью удален)
- AE test hook HTTP endpoints:
  - `/test/hook`
  - `/test/hook/{zone_id}`

---

## 2. Что переключено на canonical

- Laravel scheduler wake-up:
  - `POST /zones/{id}/start-cycle`
- UI/Proxy endpoints:
  - `GET /api/zones/{id}/state`
  - `GET /api/zones/{id}/control-mode`
  - `POST /api/zones/{id}/control-mode`
  - `POST /api/zones/{id}/manual-step`
- AE runtime endpoints:
  - `GET /zones/{id}/state`
  - `GET /zones/{id}/control-mode`
  - `POST /zones/{id}/control-mode`
  - `POST /zones/{id}/manual-step`

---

## 3. Тесты и CI

- удалены legacy тесты `backend/services/automation-engine/tests/*`.
- добавлен новый smoke baseline AE (`test_*` в корне `automation-engine`).
- добавлен отдельный replay smoke:
  - `test_scheduler_idempotency_replay.py` (duplicate accept + payload mismatch 409 по `idempotency_key`).
- CI обновлен:
  - `automation-engine-smoke` гоняет только новый smoke набор.
  - `laravel-scheduler-smoke` включает tests для `state/control-mode/manual-step`.

---

## 4. Остаточные legacy-артефакты (не runtime)

- Legacy automation e2e сценарии, требующие `ae_test_hook` инъекций (`inject_error/clear_error/reset_backoff/set_state`), удалены из `tests/e2e/scenarios/automation_engine/`.
- `tests/e2e/runner/e2e_runner.py` оставляет только `ae_test_hook action=publish_command` через `history-logger /commands`; non-publish действия удалены.
- Дефолтные launch-скрипты и `runner/suite.py` синхронизированы на AE2-Lite compatible subset:
  - `E61`, `E64`, `E65`, `E74` (full/improved/suite category),
  - `E61`, `E64`, `E65` (real-hardware suite).
- Удалены устаревшие legacy-схемы из `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME*` со старым `scheduler/task` transport.
- `tools/testing/AE2_INVARIANTS.py` расширен проверками:
  - отсутствие удаленных legacy automation-сценариев;
  - publish-only политика `ae_test_hook`;
  - отсутствие legacy automation-сценариев в launcher/suite файлах.
- Сгенерированные e2e отчеты (`tests/e2e/reports/*.xml|*.json`) удалены из git-tracking; директории сохранены через `.gitkeep`.

---

## 5. Заключение

- Runtime контур AE2-Lite очищен от legacy scheduler-task transport, legacy route aliases и legacy runtime compatibility package.
- Командный pipeline сохранен канонично:
  - `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.
- Legacy e2e fault-injection сценарии удалены; активный e2e набор соответствует каноничному AE2-Lite контракту.
