# План фиксов по итогам аудита (History-Logger / Automation-Engine / Scheduler)

Дата: 2026-02-14  
Статус: выполнено (по зафиксированным пунктам ниже)  
Решения владельца задачи:
- Контракт `history-logger`: `strict` (legacy `type` не поддерживать).
- При отсутствии доменных флагов коррекции (`flow_active/stable/corrections_allowed`): `skip`.
- Ввод safety-изменений: через `feature flag`.

## 1. Цель и рамки

Цель: устранить рассинхроны `code vs doc_ai`, закрыть критичные runtime-риски в `two_tank` ветках,
и выровнять логику коррекции под текущие спецификации без нарушения защищённого пайплайна:

`ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.

Вне рамок: breaking-изменения транспортного протокола и прямые MQTT-публикации из Laravel/scheduler/automation.

## 2. Фаза A (P1) — Runtime safety hotfix в Automation Engine

Файлы:
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`

Задачи:
1. Добавить fail-safe guard: retry/start фазы запрещён, если stop предыдущей итерации не подтверждён успехом.
2. В ветках `*_start` при `enqueue`-ошибке после успешного старта выполнять compensating `stop` до возврата terminal outcome.
3. В timeout-ветках считать завершение валидным только при подтверждённом stop (иначе `retry`/`fail` по policy).
4. Включить поведение под feature flag, например:
   - `AE_TWOTANK_SAFETY_GUARDS_ENABLED=true|false`.
5. Добавить структурированные логи: `zone_id`, `task_id`, `phase`, `correlation_id`, `stop_result`, `feature_flag_state`.

Критерии приёмки:
1. Нет переходов в `retry/start` без успешного stop.
2. Нет сценариев, где старт прошёл, enqueue упал и система осталась без stop-компенсации.
3. Все критичные ветки покрыты unit-тестами.

## 3. Фаза B (P2) — Выровнять correction logic со спецификацией

Файлы:
- `backend/services/automation-engine/repositories/recipe_repository.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_automation_service.py`
- профильные тесты automation-engine

Задачи:
1. Расширить telemetry-read модель: поднимать `flow_active`, `stable`, `corrections_allowed` (+ timestamps).
2. Ввести hard gating в correction:
   - если флаги отсутствуют/невалидны -> `skip` (как принято).
   - если флаги валидны и не проходят условия -> `skip` с reason-кодом.
3. Реализовать команды `activate_sensor_mode` / `deactivate_sensor_mode` через существующий канал:
   `Automation-Engine -> History-Logger -> MQTT`.
4. Привязать переходы correction cycle к `CORRECTION_CYCLE_SPEC.md` (без обходных shortcut-веток).

Критерии приёмки:
1. Коррекция не стартует при missing flags (только `skip`).
2. Условия `stable/corrections_allowed` реально влияют на decision.
3. Нет прямых MQTT-публикаций из AE вне `history-logger`.

## 4. Фаза C (P2) — Синхронизация документации с runtime (strict mode)

Файлы:
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`
- при необходимости связанные спецификации `doc_ai/03_TRANSPORT_MQTT/*`

Задачи:
1. Обновить контракт `history-logger`:
   - request: `cmd` (обязателен), `type` не допускается;
   - response: фактический формат (`status=ok`, `data.command_id`);
   - auth: фактическая модель по средам.
2. Исправить примеры в `ARCHITECTURE_FLOWS.md` (`cmd` вместо `type`).
3. Явно описать strict policy и примеры ошибок `400/401`.
4. Если затронуты протокол/данные на уровне спецификаций, добавить строку совместимости:
   `Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.

Критерии приёмки:
1. В `doc_ai` нет примеров с `type` для `POST /commands`.
2. Документация совпадает с фактическим поведением кода и тестами.

## 5. Фаза D (P3) — Тестовый контур и защита от регрессий

Задачи:
1. Добавить unit-тесты на fail-safe ветки:
   - enqueue fail после start -> обязательный stop rollback;
   - timeout -> retry только после успешного stop;
   - stop fail -> корректный outcome без unsafe restart.
2. Добавить tests для correction gating:
   - missing flags -> `skip`;
   - `stable=false`/`corrections_allowed=false` -> `skip`;
   - валидные флаги -> разрешённый запуск.
3. Добавить contract/integration tests для `history-logger`:
   - `cmd` required;
   - `type` rejected (strict);
   - auth-поведение по env.
4. Прогнать релевантные тестовые наборы в Docker-контуре сервисов.

Критерии приёмки:
1. Новые тесты краснеют до фиксов и зеленеют после.
2. Регрессы по критичным веткам отсутствуют.

## 6. Порядок выполнения

1. Фаза A (hotfix + feature flag + тесты).
2. Фаза B (correction gating + sensor mode + тесты).
3. Фаза C (документация strict-контракта).
4. Фаза D (финальный прогон и отчёт по покрытию рисков).

## 7. Риски и смягчение

1. Риск: временный рост `skip` в correction после включения строгого gating.  
   Смягчение: метрики причин `skip`, алерты на массовые `missing_flags`, поэтапное включение flag.
2. Риск: неожиданные интеграции зависят от `type`.  
   Смягчение: заранее объявить strict-контракт, добавить явные ошибки и примеры миграции в `doc_ai`.
3. Риск: feature flag выключен в production и hotfix неактивен.  
   Смягчение: чек-лист релиза с явной проверкой значения flag по окружениям.

## 8. Артефакты результата

1. Патчи в `automation-engine` для fail-safe поведения two_tank.
2. Патчи в correction-layer для `skip`-gating и sensor mode orchestration.
3. Обновлённые спецификации `doc_ai` по strict-контракту history-logger.
4. Набор unit/integration тестов, защищающих все критичные ветки.

## 9. Дополнительные найденные рассинхроны (итерация 2)

Состояние выполнения:
- 9.1: выполнено
- 9.2: выполнено
- 9.3: выполнено
- 9.4: выполнено
- 9.5: выполнено
- 9.6: выполнено

Подтверждение закрытия:
- 9.1: добавлен concurrent stress-test `/scheduler/task` + background housekeeping в `backend/services/automation-engine/test_api.py`.
- 9.5: для unknown `cmd_id` подтверждён pre-terminal stub (`ACK`) + terminal update через `commandAck`.
- MQTT docs синхронизированы по `command_response` статусам (`TIMEOUT` добавлен; `SEND_FAILED` явно backend-layer).

### 9.1 P1 — Cross-loop гонка между `main` и API thread в Automation Engine

Симптом:
1. FastAPI поднимается в отдельном потоке с отдельным event loop.
2. `CommandBus`/`CommandTracker`/`ZoneAutomationService` создаются в основном loop.
3. Эти объекты передаются в API и используются из другого loop.

Код:
1. `backend/services/automation-engine/main.py:765`
2. `backend/services/automation-engine/main.py:1020`
3. `backend/services/automation-engine/main.py:1039`
4. `backend/services/automation-engine/main.py:1058`
5. `backend/services/automation-engine/api.py:782`
6. `backend/services/automation-engine/api.py:801`

Риск:
1. Нестабильные runtime-ошибки loop affinity (`attached to a different event loop`).
2. Гонки по shared state tracker/service.
3. Потеря/дублирование command tracking.

План фикса:
1. Убрать cross-loop sharing: запускать API в том же loop, что и основной orchestrator, либо поднимать отдельные loop-local экземпляры `CommandBus`/`CommandTracker`/`ZoneAutomationService`.
2. Запретить использование одного `CommandTracker` из разных loop.
3. Добавить стресс-тест concurrent `/scheduler/task` + основной цикл.

Критерии:
1. Нет shared async-объектов между разными event loop.
2. Нет ошибок loop affinity под нагрузкой.

### 9.2 P1 — Retry-задачи переиспользуют исходный `correlation_id` и ломаются на idempotency

Симптом:
1. Decision-retry enqueue копирует `correlation_id` исходной задачи.
2. Scheduler пробрасывает этот `correlation_id` в новый submit.
3. `automation-engine` дедуплицирует по `correlation_id` и при изменённом payload возвращает `409 idempotency_payload_mismatch`.
4. Internal enqueue помечается `failed` и retry-цепочка обрывается.

Код:
1. `backend/services/automation-engine/scheduler_task_executor.py:760`
2. `backend/services/scheduler/main.py:2084`
3. `backend/services/scheduler/main.py:2091`
4. `backend/services/automation-engine/api.py:446`
5. `backend/services/automation-engine/api.py:507`
6. `backend/services/scheduler/main.py:1093`

План фикса:
1. Формировать новый `correlation_id` для каждого retry-шага (например, `:<retry_attempt>`).
2. Сохранять `parent_correlation_id` отдельно в payload/details для трассировки.
3. Добавить интеграционный тест: минимум 2 последовательных retry без `409`.

Критерии:
1. Retry-цепочки не падают на idempotency mismatch.
2. Корреляция сохраняется через parent-link, а не reuse одного ID.

### 9.3 P1 — TIMEOUT в closed-loop фиксируется локально, но не всегда персистится в БД

Симптом:
1. При timeout `CommandBus` вызывает `tracker.confirm_command_status("TIMEOUT")`.
2. `CommandTracker` обновляет только in-memory `pending_commands`, без SQL update статуса команды.
3. Laravel timeout-job работает только по `SENT`, не по `ACK`; зависшие `ACK` могут остаться навсегда.

Код:
1. `backend/services/automation-engine/infrastructure/command_bus.py:849`
2. `backend/services/automation-engine/infrastructure/command_bus.py:852`
3. `backend/services/automation-engine/infrastructure/command_tracker.py:152`
4. `backend/services/automation-engine/infrastructure/command_tracker.py:367`
5. `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php:32`

Риск:
1. Рассинхрон `local decision=TIMEOUT` vs `DB status=ACK/SENT`.
2. Повторные команды блокируются/диагностика неверна.

План фикса:
1. Ввести персистентный апдейт статуса `TIMEOUT`/`SEND_FAILED` в `commands` из automation path (через единую безопасную функцию слоя Python).
2. Расширить Laravel timeout-job минимум на `ACK`.
3. Для timeout-job писать `failed_at`, `error_code`, `result_code`.

Критерии:
1. Любой timeout в closed-loop отражается в БД как терминальный статус.
2. Нет «вечных ACK» после истечения timeout.

### 9.4 P1 — `commandAck` в Laravel не считает `TIMEOUT`/`SEND_FAILED` terminal и допускает rollback

Симптом:
1. Валидатор `commandAck` не принимает `TIMEOUT`/`SEND_FAILED`.
2. Эти статусы отсутствуют в `finalStatuses` и `statusOrder`.
3. При позднем ACK после timeout возможен rollback `TIMEOUT -> ACK`.

Код:
1. `backend/laravel/app/Http/Controllers/PythonIngestController.php:231`
2. `backend/laravel/app/Http/Controllers/PythonIngestController.php:268`
3. `backend/laravel/app/Http/Controllers/PythonIngestController.php:294`
4. `backend/laravel/app/Models/Command.php:46`

План фикса:
1. Добавить `TIMEOUT`/`SEND_FAILED` в валидацию, mapping, `finalStatuses`, `statusOrder`.
2. Явно запретить переходы из terminal в non-terminal.
3. Добавить feature-тест на late-ack rollback prevention.

Критерии:
1. Терминальные статусы едины в модели и контроллере.
2. Rollback terminal->non-terminal невозможен.

### 9.5 P2 — Stub-команды из `command_response` теряют terminal metadata и broadcast

Симптом:
1. При неизвестном `cmd_id` history-logger вставляет stub уже с terminal status (`DONE/ERROR/...`).
2. Дальше `commandAck` видит final status и выходит ранним return.
3. В результате могут не выставиться `ack_at/failed_at` и не пойти ожидаемые события UI.

Код:
1. `backend/services/history-logger/mqtt_handlers.py:1460`
2. `backend/laravel/app/Http/Controllers/PythonIngestController.php:268`
3. `backend/laravel/app/Http/Controllers/PythonIngestController.php:277`

План фикса:
1. Для stub вставки использовать pre-terminal статус (`SENT`/`ACK`) и доводить до terminal через `commandAck`.
2. Либо при stub-insert сразу заполнять terminal timestamps и отправлять эквивалент event.
3. Добавить тест `unknown cmd_id + DONE` на корректный terminal side-effect.

Критерии:
1. Для unknown `cmd_id` не теряются terminal timestamps.
2. UI получает консистентный terminal update.

### 9.6 P2 — Internal enqueue падает без ретрая на первой же ошибке dispatch

Симптом:
1. Любой `execute_scheduled_task(...)=False` переводит internal enqueue в `failed`.
2. Нет backoff/retry до `expires_at`, даже при временном сетевом/HTTP сбое.

Код:
1. `backend/services/scheduler/main.py:1093`
2. `backend/services/scheduler/main.py:1107`

План фикса:
1. Добавить `dispatch_retry_count` и `next_retry_at` в `details`.
2. Ретраить до `expires_at` или `max_attempts`.
3. Переводить в `failed` только по исчерпанию retry-политики или hard-invalid payload.

Критерии:
1. Временные сбои dispatch не обрывают self-task workflow.
2. Internal enqueue надёжно доходит до terminal состояния.

## 10. Дополнительные найденные рассинхроны (итерация 3)

Состояние выполнения:
- 10.1: не выполнено
- 10.2: не выполнено
- 10.3: не выполнено
- 10.4: не выполнено
- 10.5: не выполнено
- 10.6: не выполнено
- 10.7: не выполнено
- 10.8: не выполнено

### 10.1 P1 — starvation internal enqueue из-за SQL scan по `task_name` + `LIMIT`

Симптом:
1. `_load_pending_internal_enqueues()` выбирает `DISTINCT ON (task_name)` с `ORDER BY task_name, created_at DESC` и `LIMIT`.
2. `LIMIT` применяется к лексикографически первым `task_name`, а не к реально актуальным pending-задачам.
3. SQL не фильтрует pending на стороне БД, фильтр делается уже в Python.
4. При росте `scheduler_logs` возможен голод: due/pending enqueue вне первых `LIMIT` не попадают в обработку.

Код:
1. `backend/services/scheduler/main.py:983`
2. `backend/services/scheduler/main.py:987`
3. `backend/services/scheduler/main.py:992`
4. `backend/services/scheduler/main.py:1006`

План фикса:
1. Переписать загрузку pending на SQL fail-closed: сначала брать только последние записи нужного окна по `created_at`, затем выделять latest state по `task_name`.
2. Фильтровать `status='pending'` в SQL до `LIMIT`.
3. Сортировать pending-кандидаты по `scheduled_for`/`created_at`, а не по `task_name`.
4. Добавить тест > `scan_limit`: pending-задача вне лексикографического top-N обязана быть обработана.

Критерии:
1. Нет зависания pending-задач при большом объёме `scheduler_logs`.
2. Очередь internal enqueue обрабатывается по времени готовности, а не по имени.

### 10.2 P1 — потеря статусов при ошибке записи в DLQ

Симптом:
1. `move_to_dlq()` подавляет исключения и не возвращает признак успеха.
2. Вызывающий код после `move_to_dlq()` всегда делает `mark_delivered()` (delete из pending).
3. При ошибке insert в DLQ запись удаляется из pending и теряется.

Код:
1. `backend/services/common/command_status_queue.py:343`
2. `backend/services/common/command_status_queue.py:378`
3. `backend/services/common/command_status_queue.py:450`
4. `backend/services/common/command_status_queue.py:877`
5. `backend/services/common/command_status_queue.py:894`

План фикса:
1. Сделать `move_to_dlq()` transactional и возвращающим `bool` (или бросающим исключение).
2. Удалять запись из pending только после подтверждённого успеха перемещения в DLQ.
3. На `move_to_dlq`-ошибке оставлять запись в pending и увеличивать `retry_count` с backoff.
4. Добавить unit-тесты на отказ DLQ insert/update без потери данных.

Критерии:
1. Ошибки DLQ не приводят к silent data loss.
2. Для каждой недоставленной записи сохраняется либо pending, либо DLQ состояние.

### 10.3 P1 — локальный timeout в CommandTracker не всегда персистится в БД

Симптом:
1. В `_check_timeout()` локальный timeout идёт через `_confirm_command_internal(..., 'TIMEOUT')`.
2. Этот путь не вызывает `_persist_terminal_status()`, значит `commands.status` может остаться `QUEUED/SENT/ACK`.
3. В Laravel timeout-job обрабатываются только `SENT/ACK`; залипший `QUEUED` не финализируется.
4. Возможен рассинхрон: в memory `TIMEOUT`, в БД не-терминальный статус.

Код:
1. `backend/services/automation-engine/infrastructure/command_tracker.py:394`
2. `backend/services/automation-engine/infrastructure/command_tracker.py:413`
3. `backend/services/history-logger/command_routes.py:675`
4. `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php:37`

План фикса:
1. В `_check_timeout()` при локальном timeout использовать `confirm_command_status(cmd_id, 'TIMEOUT', ...)`.
2. Добавить тест на ветку `db_status=None` с проверкой вызова `mark_command_timeout` и `send_status_to_laravel`.
3. Для случая `mark_command_sent`-ошибки в history-logger ввести fail-closed policy (не возвращать `ok` без статуса SENT либо сразу переводить в SEND_FAILED с диагностикой).

Критерии:
1. Любой локальный timeout в tracker отражается в БД и Laravel.
2. Нет «вечных» `QUEUED` из timeout-ветки.

### 10.4 P2 — pre-terminal stub логика не покрывает `TIMEOUT/SEND_FAILED`

Симптом:
1. `_resolve_stub_insert_status()` считает terminal только `DONE/ERROR/INVALID/BUSY/NO_EFFECT`.
2. Для unknown `cmd_id` со статусом `TIMEOUT`/`SEND_FAILED` в БД вставляется сразу terminal.
3. `commandAck` в Laravel видит terminal и может завершиться early-return, пропуская terminal side-effects.

Код:
1. `backend/services/history-logger/mqtt_handlers.py:85`
2. `backend/services/history-logger/mqtt_handlers.py:91`
3. `backend/laravel/app/Http/Controllers/PythonIngestController.php:270`

План фикса:
1. Добавить `TIMEOUT` и `SEND_FAILED` в terminal-набор `_resolve_stub_insert_status()`.
2. Для unknown `cmd_id` всегда вставлять pre-terminal `ACK`, terminal отправлять отдельным `commandAck`.
3. Добавить тесты: `unknown cmd_id + TIMEOUT`, `unknown cmd_id + SEND_FAILED`.

Критерии:
1. Для unknown `cmd_id` не теряются terminal timestamps и broadcast side-effects.
2. Поведение одинаково для всех terminal status.

### 10.5 P2 — fail-open парсинг datetime в `/scheduler/internal/enqueue`

Симптом:
1. Невалидный `scheduled_for` silently превращается в `now`.
2. Невалидный `expires_at` silently превращается в `None`.
3. Endpoint принимает повреждённый payload вместо `422`.

Код:
1. `backend/services/automation-engine/scheduler_internal_enqueue.py:53`
2. `backend/services/automation-engine/scheduler_internal_enqueue.py:54`

План фикса:
1. Явно валидировать `scheduled_for` и `expires_at`: при невалидном формате выбрасывать `ValueError`.
2. Добавить негативные тесты на invalid datetime для `scheduled_for`/`expires_at`.
3. Сохранить текущую логику по UTC-нормализации, но убрать silent fallback.

Критерии:
1. Невалидные datetime всегда дают `422`.
2. Нет скрытого изменения смысловой даты запуска/истечения.

### 10.6 P1 — orphan accepted-task при сбое `create_zone_event` в `/scheduler/task`

Симптом:
1. `task` создаётся и snapshot персистится до `create_zone_event`.
2. Если `create_zone_event` бросает исключение, запуск `_execute_scheduler_task()` не происходит.
3. Повтор с тем же `correlation_id` возвращает duplicate и не инициирует исполнение повторно.
4. Возможна «зависшая» `accepted/running` задача без фактического execution.

Код:
1. `backend/services/automation-engine/api.py:1117`
2. `backend/services/automation-engine/api.py:1145`
3. `backend/services/automation-engine/api.py:1159`

План фикса:
1. Перенести `asyncio.create_task(_execute_scheduler_task(...))` до non-critical event side-effect либо обернуть `create_zone_event` в try/except без прерывания execution.
2. Для duplicate `accepted/running` добавить self-heal: если активного execution нет, запускать re-dispatch.
3. Добавить тест на исключение в `create_zone_event` без потери запуска задачи.

Критерии:
1. Ошибка event-log не блокирует фактическое исполнение scheduler-task.
2. Duplicate по `correlation_id` не фиксирует «мертвый accepted».

### 10.7 P1 — `history-logger` возвращает `ok` при сбое фиксации `SENT` в БД

Симптом:
1. После успешной MQTT публикации выполняется `mark_command_sent(...)`.
2. При исключении в `mark_command_sent` ошибка только логируется, но endpoint всё равно возвращает `200 ok`.
3. Команда может остаться в `QUEUED`/`SEND_FAILED` при фактической отправке на устройство.
4. Если ответ ноды не придёт, `QUEUED` не финализируется timeout-job'ом Laravel (он обрабатывает `SENT/ACK`).

Код:
1. `backend/services/history-logger/command_routes.py:674`
2. `backend/services/history-logger/command_routes.py:696`
3. `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php:37`

План фикса:
1. Сделать переход в `SENT` fail-closed: при ошибке state-sync не возвращать `200 ok`.
2. Возвращать явный transport/error (`5xx`) с кодом `command_state_sync_failed`.
3. Добавить тесты на ветку: publish success + ошибка `mark_command_sent` => неуспешный HTTP ответ и infra-alert.

Критерии:
1. Невозможно получить `ok` при несогласованном command-state в БД.
2. Нет зависания команд в `QUEUED` из-за silent ошибки post-publish.

### 10.8 P1 — `/scheduler/internal/enqueue` может создать pending-задачу и вернуть 500 (дубликаты при ретрае)

Симптом:
1. `enqueue_internal_scheduler_task()` сначала пишет pending-log в `scheduler_logs`.
2. Затем пишет `SELF_TASK_ENQUEUED` через `create_zone_event`.
3. Если `create_zone_event` падает, endpoint отвечает ошибкой, хотя pending-log уже сохранён.
4. Клиентский retry создаёт новый `enqueue_id` и вторую pending-задачу (дубликат workflow).

Код:
1. `backend/services/automation-engine/scheduler_internal_enqueue.py:76`
2. `backend/services/automation-engine/scheduler_internal_enqueue.py:77`
3. `backend/services/automation-engine/scheduler_internal_enqueue.py:88`

План фикса:
1. Считать `create_scheduler_log` критичным side-effect, `create_zone_event` — best-effort (try/except без отмены enqueue).
2. Добавить идемпотентность internal enqueue по `correlation_id` (или обязательный `correlation_id`) для безопасных повторов.
3. Добавить тест: сбой `create_zone_event` не должен приводить к 500 и дубликатам enqueue.

Критерии:
1. Ошибка event-log не приводит к повторной постановке той же self-task.
2. Повтор запроса с тем же `correlation_id` не создаёт новый `enqueue_id`.
