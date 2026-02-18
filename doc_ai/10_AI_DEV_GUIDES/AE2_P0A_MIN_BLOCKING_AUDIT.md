# AE2_P0A_MIN_BLOCKING_AUDIT.md
# AE2 S1: минимальный blocking audit

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Invariants (обязательные)
1. Команды к нодам публикуются только через `history-logger`.
2. Прямая MQTT-публикация из `automation-engine`, `scheduler`, `laravel` запрещена.
3. Защищенный поток команд: `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.
4. Защищенный поток телеметрии: `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.
5. Изменения БД допускаются только через Laravel migrations.

## 2. Command Flow Map (фактические publish paths)
1. Runtime correction path:
- `services/zone_correction_orchestrator.py`
- `correction_controller.py`
- `correction_command_retry.py`
- `infrastructure/command_bus.py`

2. Scheduler task path:
- `api.py` (`POST /scheduler/task`)
- `application/api_scheduler_execution.py`
- `application/scheduler_executor_impl.py`
- `application/command_publish_batch.py`
- `infrastructure/command_bus.py`

3. Controller action path:
- `services/zone_controller_processors.py`
- `services/zone_controller_execution.py`
- `infrastructure/command_bus.py`

4. Internal enqueue continuation path:
- `scheduler_internal_enqueue.py`
- `api.py` (`/scheduler/internal/enqueue`)
- далее через scheduler-task lifecycle.

5. Legacy deprecated path (под удаление в S8):
- `main.py:publish_correction_command()`.

## 3. Ownership Map (минимальный)
1. `backend/services/automation-engine/application/executor_bound_*`:
- зона: scheduler execution orchestration helpers.
- риск: высокая скрытая связанность и размытые границы ответственности.

2. `backend/services/automation-engine/api.py`:
- зона: ingress/transport/runtime wiring.
- риск: крупный orchestration surface.

3. `backend/services/scheduler/main.py`:
- зона: планирование, dispatch, bootstrap/heartbeat, leader/catchup.
- риск: монолитный runtime entrypoint.

## 4. Ownership decision: `check_phase_transitions`
Решение S1:
1. `check_phase_transitions` остается **только simulation-path**.
2. В `live` режиме функция остается no-op и не считается runtime owner path.
3. Любое расширение в production path требует отдельного ADR до начала S8.

## 5. Blocking risk register (S1)
1. Dual-writer риск publish side effects (scheduler-path + loop path).
2. Недостаточная формализация safety bounds на уровне correction-controller.
3. Неполная формализация runtime-state ownership между крупными модулями.

## 6. Gate verdict
S1 verdict: `PASS_WITH_ACTIONS`.

Обязательные follow-up шаги перед глубокими миграциями:
1. Mini-S2 safety research (decision-complete).
2. S3 safety implementation (bounds + rate-limit + fail-closed audit trails).
3. Обновление `AE2_CURRENT_STATE.md` после каждого stage.
