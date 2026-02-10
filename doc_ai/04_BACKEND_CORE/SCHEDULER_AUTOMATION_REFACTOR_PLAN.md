# SCHEDULER_AUTOMATION_REFACTOR_PLAN.md

Дата: 2026-02-10

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель

Перевести `scheduler` в роль чистого планировщика:
- только построение расписаний;
- отправка абстрактных задач в `automation-engine`;
- ожидание статусов `accepted/completed|failed`.

Исполнение команд на узлы, safety-проверки, контроль параметров и коррекции должны выполняться только в `automation-engine`.

## 2. Результат аудита (факт на дату)

### 2.1 Что было в scheduler

- Формировал расписания из `effective-targets`.
- Отправлял device-level команды (`run_pump`, `light_on/off`) через `automation-engine /scheduler/command`.
- Делал safety-логику и инфраструктурный контроль (уровень воды, dry-run мониторинг, water-change orchestration).

### 2.2 Что было в automation-engine

- Имел endpoint `POST /scheduler/command` для device-level команд.
- Централизованно отправлял команды через `CommandBus` -> `history-logger`.
- Основная автоматизация параметров уже была внутри `ZoneAutomationService`.

### 2.3 Разрыв ответственности

- Scheduler выполнял часть автоматизации и safety, что конфликтует с целевой архитектурой.
- Не было task-level контракта `scheduler -> automation-engine` с жизненным циклом `accepted/completed`.

## 3. Выполненные изменения

### 3.1 Scheduler (planner-only)

- Удалено прямое управление устройствами и safety/аварийная логика.
- Добавлена отправка абстрактных задач через `POST /scheduler/task`.
- Добавлено ожидание статуса задачи через `GET /scheduler/task/{task_id}`.
- Поддержаны типы задач: `irrigation`, `lighting`, `ventilation`, `solution_change`, `mist`, `diagnostics`.
- Добавлены метрики task-статусов и диагностика ошибок task API.

### 3.2 Automation-engine

- Добавлен task-level API:
  - `POST /scheduler/task`
  - `GET /scheduler/task/{task_id}`
- Добавлен исполнитель `scheduler_task_executor.py`:
  - маппинг абстрактных задач на исполнение через `CommandBus`;
  - fallback в `ZoneAutomationService` для диагностических сценариев.
- Добавлен конфигурационный слой маппинга `config/scheduler_task_mapping.py`
  с override из `payload.config.execution` (без hardcode в executor).
- Добавлена персистентность task-снимков (`accepted/running/completed/failed`)
  через `scheduler_logs` с восстановлением статуса после рестарта.
- Добавлена регистрация `ZoneAutomationService` в API из `main.py`.

### 3.3 Тесты

Добавлены/обновлены тесты:
- `backend/services/scheduler/test_main.py`
- `backend/services/automation-engine/test_api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`

## 4. План дальнейшей переработки (следующий этап)

1. Добавить startup-handshake (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) и safe-mode scheduler до `ready`.
2. Сделать `correlation_id` обязательным и реализовать persistent dedupe/idempotency в `automation-engine`.
3. Добавить decision-layer outcome в task-result (`action_required`, `decision`, `reason_code`, `error_code`).
4. Реализовать internal enqueue для self-task (`automation-engine` -> `scheduler`) для отложенных проверок.
5. Добавить детализированные события задачи для фронтенда (task timeline), обновить backend/UI отображение lifecycle и SLA.

## 5. Матрица ответственности после рефакторинга

- `scheduler`: расписания + task dispatch + ожидание task статуса.
- `automation-engine`: принятие задачи, оркестрация исполнения, команды узлам, автоматизация параметров, safety/коррекции.
- `history-logger`: приём команд и доставка в MQTT pipeline.
