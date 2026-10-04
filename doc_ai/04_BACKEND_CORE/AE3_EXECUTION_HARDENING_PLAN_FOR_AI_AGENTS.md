---
name: План исправления архитектуры исполнения AE3 для ИИ-агентов
description: Последовательное устранение дефектов AE3, обновление регрессионных тестов и проверка исполнения в Docker.
version: 1.0.0
last_updated: 2026-10-03
maintained_by: Hydro 2.0
status: plan
---

# План исправления архитектуры исполнения AE3 для ИИ-агентов

**Статус:** реализация начата; приёмка этапов ведётся ниже.
**Основание:** [архитектурный аудит](AE3_ARCHITECTURE_REVIEW.md), commit аудита `3c04c3fe`.
**Роль исполнителя:** разработчик Python/asyncio/PostgreSQL, отвечающий за корректность управления оборудованием, совместимость контрактов и регрессионные тесты.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель и ожидаемый результат

Исправить F1–F6 из аудита и последовательно укрепить существующий AE3:

1. Все ошибки активного исполнения проходят согласованную политику безопасного завершения.
2. Потерявший владение исполнитель не может сохранить stale outcome или продолжить обычную командную последовательность.
3. Task и workflow state меняются атомарно.
4. Тайм-ауты и составные snapshots имеют явную, проверяемую семантику.
5. Повторная доставка команды не меняет её смысл и не создаёт дополнительную дозу.
6. Обычное исполнение и recovery используют общие операции перехода и сверки результатов.
7. Регрессионные тесты добавлены/исправлены, обязательные прогоны завершены, результаты записаны.

Выполнение плана означает **код + исправление тестов + запуск тестов + устранение выявленных падений + обновление затронутых контрактов**. Одного рефакторинга файлов или списка рекомендованных проверок недостаточно.

Этот план не заменяет [canonical AE3](ae3lite.md). В отчёте аудита ранее прошли 359 выбранных тестов; это исторический baseline, а не подтверждение выполнения данного плана.

## 2. Обязательный контекст и ограничения

До работы прочитать корневой `AGENTS.md`, `backend/services/AGENTS.md`, `backend/services/automation-engine/AGENT.md`, `doc_ai/INDEX.md`, `SYSTEM_ARCH_FULL.md`, `ARCHITECTURE_FLOWS.md`, `DEV_CONVENTIONS.md` и аудит.

Дополнительный контекст по этапу:

| Изменение | Документы |
|---|---|
| Execution/FSM/recovery | [ae3lite.md](ae3lite.md), [IRR safety](AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md), [runtime events](AE3_RUNTIME_EVENT_CONTRACT.md) |
| БД/snapshot | [модель данных](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md), [read-model](LARAVEL_AE3_READ_MODEL_CONTRACT.md), [authority](AUTOMATION_CONFIG_AUTHORITY.md) |
| Команды | [history-logger API](HISTORY_LOGGER_API.md), [MQTT contract](../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md) |
| Коррекция | [correction](../06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md), [targets](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md), [PID](../06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md) |
| Климат | [greenhouse climate](../06_DOMAIN_ZONES_RECIPES/GREENHOUSE_CLIMATE_CONTROL_PLAN.md) |
| E2E | `tests/e2e/AGENTS.md`, [E2E guide](../13_TESTING/E2E_GUIDE.md) |

Ограничения:

- По поручению пользователя от 2026-10-04 оставшуюся реализацию и приёмку выполняет ведущий агент самостоятельно, без запуска субагентов. Тесты с общей `hydro_test` запускаются строго по одному. Production остаётся с одной активной репликой AE3.
- Сохранить pipeline `Laravel scheduler-dispatch → AE → history-logger → MQTT → ESP32`. Не публиковать MQTT напрямую.
- Не создавать новый сервис, task type, authority document type, параллельный runtime, универсальную workflow/outbox-платформу или редактор графов.
- Python/backend/БД/E2E запускать в Docker. Тесты AE/Laravel — `hydro_test`, YAML E2E — отдельный `hydro_e2e`.
- Изменения схемы — Laravel migrations. Перед изменением защищённого контракта обновлять соответствующую спецификацию; несовместимость отдельно согласовывать, а не объявлять совместимой.
- Не менять химическую политику, PID-коэффициенты и состав доз в рамках структурного рефакторинга.
- Сохранить locked/live semantics, stage deadlines, E-Stop, manual/semi режимы, no-effect и ownership ограничений устройств.
- Не удалять пользовательские изменения и тестовые данные других запусков. Не применять `reset-db`, `test-db-reset`, `migrate:fresh` или общий destructive cleanup.
- Не поднимать digital-twin, feature-builder или node-emulator как зависимость обычных AE-тестов.

## 3. Порядок исполнения и журнал

Строго следовать зависимости `S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8`. Перед этапом назвать конкретные файлы и выбранное решение; после этапа запустить его тесты. Не переходить далее при необъяснённом падении обязательной проверки.

| Этап | Область | Статус |
|---|---|---|
| S0 | Baseline и сверка контрактов | Завершён: `make test-ae PYTEST_ARGS='-q --tb=short'`, exit 0, 7 crash-window + 1601 passed (52.98 s), лог `/tmp/ae3-hardening-baseline.log`; HEAD `3c04c3fe` |
| S1 | Failure boundary и loss lease: F1/F4 | Завершён, commit нет. Diff на HEAD `3c04c3fe`: `execute_task.py`, `worker.py`, `flow_path_guard.py`, `run_tick.py`, узкий fan-out в `sequential_command_gateway.py`, `correction_interrupt_safety.py` (`confirmed=False`, reason `publish_accepted_unconfirmed`), тесты группы A и `test_ae3lite_s1_failure_boundary.py`, контракты `ae3lite.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`, `ERROR_CODE_CATALOG.md`. Приёмка ведущего: повторный прогон группы A + новый файл, exit 0, 107 passed, 0 failed, 0 skipped. Остаток: `success=True` у publish-only по-прежнему означает приём транспорта, не OFF; полный `make test-ae` отложен до S8 |
| S2 | Строгое владение исполнением: F2 | Реализован: общая sequence поколения, atomic claim task+lease, CAS writes, запрет stale writer и заимствования свежего token. PostgreSQL regressions входят в 51 passed; финальная проверка S8 ниже. |
| S3 | Атомарность task/workflow: F3 | Реализован: TaskWorkflowTransition использует общий connection для task/workflow/intent heartbeat; normal и recovery используют одну операцию. PostgreSQL rollback/success/manual-step regressions входят в 51 passed; финальная проверка S8 ниже. |
| S4 | Согласованный snapshot: F6 | Принят: REPEATABLE READ READ ONLY, реальный concurrent commit между SELECT. Snapshot + schema/idempotency группа: 115 passed, exit 0. |
| S5 | Семантика дедлайнов: F5 | Реализован: persisted overall_deadline_at, отдельный бюджет 7 суток от first claim, manual wait входит; overdue pending выбирается до due_at; clock guard перед HTTP; timeout ведёт в общий safety-path. Persistence/restart/clock regressions включены в проверенные группы 68 и 51 passed. |
| S6 | Неизменяемые команды и crash recovery | Реализован: immutable node/channel/cmd/params при retry, stable cmd_id, проверка ownership перед HTTP, DONE не заимствует новую generation. Командная группа: 65 passed; расширенные регрессии 51 passed. Финальная проверка S8 ниже. |
| S7 | Декомпозиция и единые операции исполнения | Реализована ограниченная декомпозиция: общий TaskWorkflowTransition для normal/recovery, общий pure CommandOutcome и persist результата, единый failure path worker/use-case с отдельным состоянием каждого claim. Химические алгоритмы и долгие observe loops не переписывались. |
| S8 | Полный прогон, исправление падений, handoff | Завершён 2026-10-04: полный AE 1665 passed + отдельные 7 crash-window, Laravel 95 passed (390 assertions), E95–E99 5/5 passed. Все exit 0, без skip в приёмочных наборах. Pint 4 files PASS, diff --check PASS. Детали и ограничения в §16. |

При завершении этапа рядом со статусом добавить: commit или описание diff, изменённые файлы, команды, exit codes, passed/failed/skipped, путь к отчётам и остаточные риски. Статус «Завершён» допустим только при выполненной приёмке. При внешнем blocker записать точную ошибку и незавершённые проверки; не считать этап зелёным.

## 4. S0 — проверить актуальность аудита и получить baseline

1. Проверить `git status`, HEAD, локальные инструкции и фактические имена тестов. Сохранить существующий diff.
2. Прочитать текущие реализации F1–F6: аудит мог устареть. Если дефект уже исправлен — подтвердить регрессией, не воспроизводить старый дизайн.
3. Проверить Docker и подготовить `hydro_test` через существующий `make test-db-init`. Прочитать актуальный Makefile перед запуском: target зависит от core `up` и применяет Laravel migrations.
4. Выполнить baseline полного AE suite командой из §13. Записать исходные падения отдельно от новых регрессий. До baseline-изменений не править тесты ради зелёного статуса.
5. Зафиксировать обнаруженный drift, в том числе irrigation pH-only против разрешённого EC `calcium|npk`. Не решать этот продуктовый вопрос скрытым изменением runtime.

**Приёмка:** воспроизводимый baseline и список применимых дефектов. Если существующий тест утверждает ошибочное поведение, отметить его как подлежащий замене в соответствующем этапе.

## 5. S1 — единая граница отказа и отказ продолжать после loss lease

**Файлы:** `ae3lite/application/use_cases/execute_task.py`, `runtime/worker.py`, `application/handlers/flow_path_guard.py`, `greenhouse_climate/run_tick.py`; связанные recovery/finalize методы по необходимости.

**Реализация:**

1. Включить preflight в failure boundary. После уже выполненной стадии ошибка построения snapshot/preflight не должна обходить необходимый safety-path.
2. Устранить аварийную ветку worker, которая считает запись `failed` достаточной остановкой. Использовать общий механизм завершения, не дублировать набор исключений в каждом слое.
3. Обеспечить stop-попытку на доступных устройствах даже при отказе другого узла; не требовать успешного полного snapshot для самой возможности остановки. Если адреса или результат недостоверны — сохранять неопределённость, а не выдумывать подтверждение OFF.
4. Климат: `lease_renew=False` и исчерпание разрешённых transient retry должны прекращать дальнейшие обычные команды. Не допускать перехода ко второй форточке или записи успешного task outcome старым исполнителем. Учесть доменную политику ветра/дождя; hydraulic all-off сюда не переносить.
5. Различать retry транспортной ошибки heartbeat и подтверждённую потерю владения. Не продолжать работу на заведомо чужой lease.
6. При неподтверждённом stop проверить сохранение запрета опасного повторного запуска через существующие guard/alert механизмы. Если требуется новое поле safety state — сначала описать контракт и добавить миграцию; terminal failed само по себе не равно safe.

**Тесты — исправить и добавить:**

- Preflight exception на check-stage после ранее включённого потока → safety-path вызван, новая доза не отправлена.
- То же при `snapshot=None`, ошибке stop, потере связи с БД; результат не утверждает подтверждённую остановку.
- Повторный вызов обработки отказа не создаёт бесконечный цикл stop/fail и не восстанавливает обычное исполнение.
- Loss lease между левой и правой форточкой → вторая команда отсутствует; `DONE` первой не превращает задачу в успешную.
- Cancel/timeout/shutdown проходят предназначенную им политику; не поглощать произвольный `CancelledError`.

**Запуск:** группа A (§13). **Приёмка:** новая негативная регрессия падает на старой реализации и проходит после исправления; проверяется фактический список команд записывающего транспорта.

## 6. S2 — право записи связано с конкретным захватом

**Файлы:** `application/use_cases/workflow_router.py`, `claim_next_task.py`, `runtime/worker.py`, `runtime/env.py`, `infrastructure/repositories/automation_task_repository.py`, `zone_lease_repository.py`, gateway/publish path и recovery; Laravel migrations при необходимости.

**Реализация:**

1. Убрать подстановку свежего чужого `claimed_by` в stale execution context. Смена владельца означает прекращение текущего исполнения.
2. Ввести уникальную идентичность запуска процесса и неизменяемую идентичность каждого claim. Process UUID недостаточен для повторных claim одним процессом: нужен generation/token либо эквивалентная проверяемая версия.
3. Для mutation проверять исходный claim и ожидаемую версию состояния. Не подменять старый snapshot новым owner, сохраняя старый outcome.
4. Согласовать task claim и zone lease: предпочтительно одной короткой транзакцией. Не оставлять задачу claimed без lease после ошибки; откат проверять реальной БД.
5. Протянуть идентичность через heartbeat, transitions, command allocation, release и recovery. Release старого поколения не должен снимать новую lease.
6. Команды остановки после потери владения не должны конфликтовать с новым исполнителем: явно определить, кто имеет право на recovery/stop. Не добавлять неограниченный bypass ownership для обычных команд.
7. Не заявлять end-to-end fencing MQTT на основании локальной проверки перед HTTP. Изменение HL/firmware протокола выходит за первый этап укрепления single-replica runtime.

**Тесты:**

- Заменить `test_router_enter_correction_reloads_owner_from_db_when_stale`: новый результат — stale writer не пишет, а не «использует w-fresh».
- A вычислил outcome → B получил новый claim → A сохраняет: отказ; данные B не изменены.
- Повторный claim того же process owner с другим generation также отвергает старый outcome.
- Старый heartbeat/release не продлевает и не удаляет lease нового поколения.
- Два конкурентных claim через отдельные PostgreSQL connections дают одного владельца. Использовать barrier/Event, не случайные sleep.
- Recovery и operator paths соблюдают те же ограничения.

**Запуск:** группа B. **Приёмка:** PostgreSQL доказывает отсутствие stale mutation; тест двух connections не считается разрешением нескольких production-реплик.

## 7. S3 — атомарная запись переходов

**Файлы:** `application/use_cases/workflow_router.py`, `finalize_task.py`, `infrastructure/repositories/automation_task_repository.py`, `zone_workflow_repository.py`, `zone_intent_repository.py`, `domain/services/workflow_state_sync.py`.

**Реализация:**

1. Ввести одну операцию сохранения stage/correction/workflow phase в общей PostgreSQL-транзакции с единым connection и ownership/CAS из S2.
2. Удалить компенсационный `update_stage`, вызываемый после сброса owner в pending. Не исправлять его ослаблением WHERE.
3. При sync/CAS ошибке откатывать весь переход; не публиковать наружу событие успешного перехода до commit.
4. Определить принадлежность каждой записи: обязательный прогресс — транзакция; необязательные логи — после commit; пропущенный audit/event либо восстанавливается, либо явно наблюдаем.
5. Синхронизация intent должна иметь явную модель: атомарный terminal при общей БД либо проверенный идемпотентный reconcile. Нельзя терять intent lifecycle при неудаче записи.
6. Исключить HTTP и ожидание оборудования из транзакции. Соблюдать единый порядок locks и retry всей транзакции при соответствующих DB errors.

**Тесты:**

- Ошибка после task UPDATE, но до workflow UPDATE → обе строки прежние после rollback.
- Workflow CAS miss → task не переходит в новую стадию.
- Успех → обе строки согласованы; повтор операции не пересылает команды.
- Конкурентное manual-step/control-mode изменение не теряется.
- Terminal task и intent после повторного reconcile сходятся к одному результату.
- Исправить `test_router_fails_closed_when_workflow_repo_sync_fails_after_transition`: проверять реальное состояние БД, не число вызовов mock rollback.

**Запуск:** группа C. **Приёмка:** fail injection с настоящим PostgreSQL; task нельзя увидеть committed в новой стадии при старой обязательной workflow phase.

## 8. S4 — согласованный snapshot

**Файлы:** `infrastructure/read_models/zone_snapshot_read_model.py`, `laravel_schema_contract.py`, связанные snapshot DTO и builder.

1. Явно задать подходящую изоляцию короткой read-only транзакции, например `repeatable_read`, либо доказать согласованность одного SQL statement.
2. Проверить отсутствие скрытых write внутри read-path. Не удерживать snapshot-транзакцию во время HTTP или observe window.
3. Сохранить bundle revision, calibration и freshness guards. Старый согласованный snapshot не даёт права игнорировать текущие E-Stop/lease перед командой.

**Тесты:** конкурентный commit конфигурации между двумя SELECT не смешивает revisions; bundle mismatch и stale telemetry продолжают закрывать исполнение; API shape не меняется.

**Запуск:** группа D. **Приёмка:** тест с двумя connections и управляемыми барьерами, а не assert аргумента `transaction()` на mock.

## 9. S5 — четыре вида дедлайнов

**Файлы:** `runtime/worker.py`, `runtime/env.py`, `application/use_cases/workflow_router.py`, `execute_task.py`, stale/startup recovery, task entity/repository, Laravel migrations и schema contract при необходимости.

1. До кода зафиксировать в canonical spec: лимит одного tick, deadline команды, deadline стадии, deadline всей задачи; определить старт отсчёта и судьбу operator/manual ожидания.
2. Общий deadline хранить персистентно и не сбрасывать на poll, transition, claim, restart и hot reload. Определить backfill для существующих задач.
3. Проверять истечение при claim/resume и перед новым эффектом; timeout завершать через safety-path S1.
4. Согласовать бюджет с длительными стадиями и scheduler stale policy. Не превращать нынешние 900 секунд на tick в неожиданный лимит всей подготовки без анализа действующих настроек и обновления контракта.
5. Для in-process ожиданий использовать monotonic time, для persisted deadline — UTC; clock передавать явно в тестах.

**Тесты:** много коротких requeue исчерпывают общий бюджет; restart не продлевает его; independent stage/command timeout; manual ожидание следует выбранному контракту; hot reload не открывает новый бюджет; истечение при активном потоке не обходит stop.

**Запуск:** группы A/C и новые deadline-тесты. **Приёмка:** виртуальные часы без многоминутного sleep, плюс PostgreSQL persistence; все четыре семантики явно документированы.

## 10. S6 — неизменяемые команды и повтор после сбоя

**Файлы:** `infrastructure/repositories/ae_command_repository.py`, `infrastructure/gateways/command_publish_pipeline.py`, `sequential_command_gateway.py`, `application/use_cases/publish_planned_command.py`, startup/waiting reconcile.

1. Повтор pending/published_unconfirmed команды обязан сохранять node/channel/cmd/params. Несовпадение payload при прежней identity — явный конфликт; не перезаписывать старую строку новым планом.
2. Identity должна различать повтор доставки и новый осознанный импульс; учесть повторный вход той же стадии и correction attempt.
3. Сохранить stable cmd_id и сверять неоднозначный результат HL перед новой дозой. Неизвестный transport outcome не приравнивать к «не опубликовано».
4. Запись намерения выполнить эффект согласовать с прогрессом задачи; публикацию выполнять после commit. Продолжить использовать `ae_commands`, не добавлять общую event/outbox-платформу.
5. Применение DONE сделать идемпотентным, включая обновления `pid_state`, счётчиков и переходов. `ACK` не означает DONE.

**Тесты:** сбой до HTTP, после принятия HL до link, после DONE до перехода; повтор DONE; одинаковая identity с изменённой дозой; новый импульс в той же стадии; partial batch; потеря ownership перед публикацией; ожидающий эффект после restart.

**Запуск:** группа E; correction integration при затронутом PID persistence. **Приёмка:** число записанных физических намерений и опубликованных cmd_id совпадает с ожидаемым; повтор не добавляет новую дозу. Не ограничиваться terminal статусом task.

## 11. S7 — декомпозиция без изменения алгоритмов

**Файлы:** `handlers/base.py`, `handlers/correction.py`, `application/services/*`, `application/dto/stage_outcome.py`, worker/router/recovery и bootstrap.

1. Использовать существующие `DecisionWindowReader`, `SensorModeController`, `CorrectionTransitionPolicy`, `TopologyPack` и planner. Расширять их при необходимости вместо дублирования.
2. Отделить вычисление решения от SQL/HTTP/sleep. Явные зависимости наблюдения, конфигурации, safety и команд заменить неограниченный рост BaseStageHandler.
3. Объединить применение результата команды/перехода и завершение задачи для обычного исполнения и recovery. Разные триггеры recovery могут остаться отдельными.
4. Персистентные ожидания освобождают coroutine, но сохраняют запрет другой активной задаче управлять зоной. Не менять механически wait-loop без проверки lease/admission.
5. Переносить по одному поведению с регрессиями. Удалять заменённый код в том же изменении; не оставлять второй путь «на всякий случай».

**Тесты:** идентичный state/observation/config/time даёт идентичное решение; запись replay и обычного запуска сходится; restart hold/no-effect/partial batch; manual/semi/E-Stop; все текущие topology.

**Запуск:** группа F и затронутые группы A–E. **Приёмка:** сохранены command payload, последовательность химических шагов и guards; уменьшено число владельцев перехода, а не только длина файлов.

## 12. S8 — исправить падения и завершить проверку

1. Выполнить полный AE suite и обязательные Laravel/E2E проверки из §13.
2. Разбирать каждый сбой по §14. Исправлять реализацию, тест либо окружение на основании контракта и воспроизведения; повторять сначала упавший тест, затем затронутую группу.
3. После последней runtime-правки выполнить полный AE suite на итоговом дереве. После зелёного результата не повторять проверки без новых изменений или признаков нестабильности.
4. Синхронизировать canonical-документы, README сервиса, error catalog и schema contract с изменениями. Документирование контрактов выполняется и на каждом предыдущем этапе, а не откладывается до S8.
5. Проверить `git diff --check`, отсутствие тестовых артефактов/секретов и незапрошенных инфраструктурных изменений.
6. Заполнить журнал и handoff; не объявлять завершение по историческим 359 passed или по одному выбранному набору.

## 13. Команды и матрица прогонов

Все команды ниже запускаются из корня репозитория. Пути pytest относительны `/app` внутри контейнера automation-engine. Имена существующих файлов проверены при создании плана; новые регрессии добавлять в соответствующие файлы либо в отдельные tests/unit с явным именем.

Подготовка и baseline:

```bash
docker compose -f backend/docker-compose.dev.yml ps
make test-db-init
make test-ae PYTEST_ARGS="-q --tb=short"
```

`make test-ae` уже включает `test-ae-crash-windows`; не дублировать отдельный crash-window прогон, если он только что успешно выполнен этим target и код не изменился. Нельзя параллельно запускать Python и Laravel suites на одной `hydro_test`: fixtures могут конфликтовать.

Общий шаблон узкого прогона — заменить аргумент после pytest реальными файлами выбранной группы:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T \
  -e AE3_PYTEST_DB=hydro_test automation-engine pytest -q --tb=short \
  tests/unit/test_ae3lite_execute_task.py \
  tests/unit/test_ae3lite_runtime_worker_integration.py \
  tests/unit/test_ae3lite_flow_path_guard.py \
  tests/unit/test_ae3lite_lease_heartbeat_fail_closed.py \
  tests/unit/test_greenhouse_climate_tick_integration.py \
  tests/unit/test_ae3lite_worker_shutdown.py
```

| Группа | Файлы под `backend/services/automation-engine/tests/unit/` |
|---|---|
| A: failure/lease | `test_ae3lite_execute_task.py`, `test_ae3lite_runtime_worker_integration.py`, `test_ae3lite_flow_path_guard.py`, `test_ae3lite_lease_heartbeat_fail_closed.py`, `test_greenhouse_climate_tick_integration.py`, `test_ae3lite_worker_shutdown.py` |
| B: ownership | `test_ae3lite_claim_next_task.py`, `test_ae3lite_workflow_router.py`, `test_ae3lite_foreign_lease_reconcile.py`, `test_ae3lite_startup_recovery_multi_instance.py`, `test_ae3lite_runtime_worker_integration.py`, новые PostgreSQL regressions claim generation |
| C: transitions | `test_ae3lite_workflow_router.py`, `test_ae3lite_workflow_state_sync.py`, `test_ae3lite_task_requeue_from_waiting_command_integration.py`, `test_ae3lite_finalize_task.py`, `test_ae3lite_stale_task_reconcile.py`, `test_ae3lite_startup_recovery_integration.py`, новые atomic-transition regressions |
| D: snapshot | `test_ae3lite_zone_snapshot_read_model_unit.py`, `test_ae3lite_zone_snapshot_read_model_integration.py`, `test_ae3lite_zone_snapshot_freshness_fallback.py`, `test_ae3lite_zone_snapshot_diagnostics.py` |
| E: commands | `test_ae3lite_command_idempotency.py`, `test_ae3lite_ae_command_step_allocation.py`, `test_ae3lite_publish_planned_command_integration.py`, `test_ae3lite_sequential_command_gateway.py`, `test_ae3lite_startup_recovery_crash_windows.py` |
| F: domain | `test_ae3lite_correction_planner.py`, `test_ae3lite_correction_handler.py`, `test_ae3lite_correction_handler_multi_dose_integration.py`, `test_ae3lite_observation_analyzer.py`, `test_ae3lite_correction_interrupt_safety.py`, `test_ae3lite_safety_guards.py`, `test_ae3lite_workflow_topology.py`, `test_greenhouse_climate_decision_engine.py` |

Финальный AE прогон:

```bash
make test-ae PYTEST_ARGS="-q --tb=short"
```

Laravel: обязательные schema/read-model/runtime guard и затронутый scheduler/API contract. Базовый финальный набор:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T \
  -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test \
  tests/Feature/Ae3LiteSchemaTest.php \
  tests/Feature/Ae3LiteRuntimeSwitchGuardTest.php \
  tests/Feature/Contract/AutomationReadModelSchemaTest.php \
  tests/Feature/ZoneAutomationStateControllerTest.php \
  tests/Feature/ZoneAutomationStartCycleControllerTest.php \
  tests/Feature/ZoneAutomationStartIrrigationControllerTest.php \
  tests/Feature/ZoneAutomationControlModeControllerTest.php \
  tests/Feature/ZoneAutomationManualStepControllerTest.php \
  tests/Feature/ZoneAutomationOperatorUnblockControllerTest.php \
  tests/Feature/GreenhouseClimateApiTest.php \
  tests/Feature/AutomationScheduler/ScheduleDispatcherTest.php \
  tests/Feature/AutomationScheduler/SchedulerReliabilityR6Test.php
```

При migration проверить apply/rollback/reapply **только новых миграций на выделенной тестовой БД**, затем повторить schema/read-model tests. Не выполнять общий rollback чужих миграций. При изменениях Laravel применять локальные правила и профильный Laravel skill.

YAML E2E: обязательный узкий набор E95–E99 проверяет DONE, timeout, restart waiting_command, запрет runtime switch и двойного исполнения. Сначала изучить fixtures и launcher: некоторые сценарии искусственно завершают `commands`; это проверка orchestration, не физики насоса.

После подготовки **отдельного** E2E-стека и проверки его адресов/миграций выполнить:

```bash
docker compose -p e2e -f tests/e2e/docker-compose.e2e.yml run --rm --no-deps \
  e2e-runner python -m runner.suite \
  scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml \
  scenarios/ae3lite/E96_ae3_start_cycle_timeout_failed.yaml \
  scenarios/ae3lite/E97_ae3_restart_waiting_command_recovered.yaml \
  scenarios/ae3lite/E98_ae3_runtime_switch_denied_busy_zone.yaml \
  scenarios/ae3lite/E99_ae3_double_execution_guard.yaml
```

`--no-deps` намеренно исключает автоматический запуск всех зависимостей runner. До запуска проверить готовность нужных core-сервисов, test auth, migrations и только необходимых для выбранных fixtures симуляторов по E2E guide. Этот флаг не подготавливает стенд. Нельзя подставлять dev/prod адреса или запускать полный `all` для устранения ошибки подготовки. E97 перезапускает AE только изолированного проекта `e2e`.

Realhw не является частью обязательного программного прогона данного плана. При отдельно поставленной задаче читать [realhw guide](../13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md): узкий set, MQTT 1884, без node-sim. Playwright нужен только при затронутом UI; перед ним сообщить рекомендации по узкому spec/grep и артефактам только при падении.

## 14. Обязательный цикл исправления тестов

1. Сохранить точную команду, commit/рабочий diff, exit code и короткий traceback. Сначала открыть упавший тест и вызываемый runtime.
2. Классифицировать: дефект реализации; устаревший expectation; mock не моделирует SQL/CAS; некорректная fixture; проблема среды; существующая независимая ошибка.
3. Исправлять runtime, когда нарушен контракт. Менять expectation только если прежний утверждает доказанный дефект или контракт изменён явно. Причину изменения теста записывать рядом с результатом этапа.
4. Не удалять тест, не ослаблять assertion, не ставить skip/xfail и не увеличивать timeout только ради зелёного suite. Проверки ownership, shutdown, DONE, idempotency и freshness сохраняются.
5. Для БД/конкурентности использовать реальный PostgreSQL и управляемые барьеры. Mock разрешён для внешнего транспорта; список команд и payload проверять явно. Не заменять поломанный transactional тест проверкой количества вызовов.
6. Fixture создаёт свои IDs и чистит только свои строки; всегда проверять выбор тестовой БД. Пулы/connections освобождать. Не использовать live HL/MQTT в unit/integration tests.
7. Запустить упавший тест отдельно (`pytest путь::имя -q --tb=short`), затем затронутую группу. Для flaky race установить причину и проверить детерминированный сценарий; не перезапускать до случайного успеха.
8. После исправления всех релевантных падений выполнить финальный suite по S8. Независимый исходный дефект также попытаться исправить в пределах затронутого сервиса с отдельной регрессией; если это требует несовместимого/постороннего изменения — явно зафиксировать blocker, не скрывать падение.
9. Не считать collection error, отсутствие Docker/БД, пустой набор, unexpected skip или SIGKILL успешным прогоном. Выяснить причину и восстановить воспроизводимость либо отметить проверку незавершённой.

## 15. Итоговая приёмка и передача следующему агенту

- [x] F1–F6 устранены либо актуальность конкретного F опровергнута воспроизводимым тестом и зафиксированным изменением кода.
- [x] Четыре одноразовых воспроизведения аудита превращены в постоянные тесты корректного поведения.
- [x] Исправлены tests, закреплявшие подстановку чужого owner и фиктивный mock rollback.
- [x] Atomicity и ownership проверены настоящим PostgreSQL.
- [x] Нет новой дозы при неразрешённом исходе прежней команды; потеря владения останавливает обычное исполнение.
- [x] Deadline переживает requeue/restart; snapshot не смешивает версии.
- [x] Сохранены safety, correction, manual/semi, topology и pipeline contracts.
- [x] Полный AE suite, указанные Laravel tests и узкий E2E прошли на итоговом коде; пропуски объяснены и не выданы за успех.
- [x] Миграции и обновлённые спецификации проверены; удалён заменённый код.
- [x] Журнал этапов содержит команды, результаты и остаточные риски.

Формат итогового ответа агента: что исправлено; какие файлы/контракты изменены; какие тесты добавлены и почему изменены старые; команды и фактические результаты; что осталось непроверенным; следующий незавершённый этап. Не выполнять commit/push/deploy или переключение runtime на живой зоне только потому, что план завершён.

Для запуска реализации можно передать агенту:

> Выполни последовательно S0–S8 из `doc_ai/04_BACKEND_CORE/AE3_EXECUTION_HARDENING_PLAN_FOR_AI_AGENTS.md`. Исправляй код и регрессионные тесты, запускай проверки в Docker и устраняй их падения по §14. Сохраняй совместимость, обновляй журнал после каждого этапа. Не останавливайся после написания кода без обязательных прогонов; при внешнем blocker укажи точную причину и незавершённые проверки.

## 16. Приёмка ведущим агентом — 2026-10-04

Пользователь отменил дальнейший запуск субагентов; итоговые исправления и проверки
выполнены ведущим агентом. Коммит, push, deployment и физическое оборудование не затрагивались.

Исправлены найденные при приёмке дополнительные случаи: общий для всех зон recursion guard
заменён состоянием на claim; поколения разных задач больше не совпадают; heartbeat не
продлевает истёкшую lease; recovery DONE не заимствует токен нового исполнителя;
ошибка intent heartbeat внутри общей транзакции не подавляется; clock перед HTTP свежий.

Причины исправлений тестов: fixtures получили реальные claim generation/deadline параметры;
PostgreSQL timestamps сравниваются с секундной точностью схемы; workflow failure теперь
ожидается как ошибка с rollback вместо фиктивной успешной компенсации; E98 ожидает
реальный API code `validation_error` (остальные проверки busy guard сохранены).
Snapshot схемы заново сформирован Laravel: дополнительно отражает ранее отсутствовавшие
в сохранённом snapshot существующие correction-колонки; новые миграции их не создают.

Проверки и логи:

- `make test-ae PYTEST_ARGS='-q --tb=short'`: **1665 passed (58.83 s)** плюс отдельный прогон **7 crash-window passed**, exit 0, лог `/tmp/ae3-final-pass.log`.
- Laravel — команда §13 с `-e APP_ENV=testing -e DB_DATABASE=hydro_test` и дополнительным
  `tests/Feature/Ae3ExecutionHardeningMigrationTest.php`: **95 passed, 390 assertions**,
  exit 0, `/tmp/ae3-laravel-verified.log`. Проверены down/up только трёх новых migrations
  внутри откатываемой транзакции на `hydro_test`. Первоначальный запуск без явных env
  был отклонён guard для `local/hydro_dev`; исправлено окружение, guard не ослаблялся.
- Schema generator — `UPDATE_SCHEMA_SNAPSHOT=1 ... AutomationReadModelSchemaTest`;
  его один служебный skip означает генерацию, не приёмку. Последующий schema test
  входит в 95 passed без skip.
- Pint: четыре новых PHP-файла, exit 0, `/tmp/ae3-pint.log`.
- E2E — команда §13 с `-vv`: **5/5 passed**, exit 0, `/tmp/ae3-e2e-verified.log`.
  Сценарии E95–E99 выполнены на отдельном `hydro_e2e` с пересобранным AE image.
  Есть прежние предупреждения optional cleanup об удалённой таблице `grow_cycle_overrides`;
  обязательные действия/assertions прошли. Проверка restart ожидаемо повторяет health
  request, пока AE поднимается. Это orchestration-тесты с искусственным DONE/TIMEOUT,
  а не подтверждение физического OFF.

Ограничения приёмки: production rollout/rollback и realhw не выполнялись; multi-replica
не поддерживается. Успешная публикация stop остаётся транспортным подтверждением.
S7 ограничен объединением операций перехода, результата команды и отказа; большой
перенос всех методов BaseStageHandler/CorrectionHandler и изменение coroutine wait loops
не нужны для исправления F1–F6 и в этой дельте не выполнялись.
