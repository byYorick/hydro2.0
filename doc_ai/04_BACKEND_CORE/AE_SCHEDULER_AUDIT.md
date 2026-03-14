# Глубокий аудит Automation Engine + Scheduler

**Дата:** 2026-03-13
**Ветка:** ae3
**Scope:** automation-engine (Python), scheduler (Laravel + Python)

---

## Резюме

Проведён комплексный аудит 4 направлений:
1. Архитектура и баги AE
2. Scheduler (Laravel + Python)
3. Покрытие тестами
4. Интеграция между сервисами

**Общая оценка:** Кодовая база зрелая и хорошо структурированная. После сверки документа с актуальным кодом часть исходных замечаний переквалифицирована: подтверждены несколько практических проблем, часть пунктов оказалась устаревшей, а часть относится скорее к hardening/observability, чем к production bug.

---

## 1. БАГИ

### BUG-1: [MEDIUM] PID state и correction state разнесены по разным DB операциям
**Файл:** `ae3lite/application/handlers/correction.py:206-210`

Исходная формулировка была неточной. По текущему коду при падении `_persist_pid_state_updates()` correction state **не** продвигается: handler завершится исключением до формирования `StageOutcome`, а `update_stage()` не будет вызван.

Реальный риск обратный: PID state (integral, prev_error, prev_derivative) сохраняется отдельным upsert до записи нового correction state. Если upsert PID уже прошёл, а последующий `update_stage()`/requeue сорвётся, следующая попытка увидит обновлённую PID-память при старом correction state.

```python
# Строка 208: PID state сохраняется отдельно
await self._persist_pid_state_updates(zone_id=task.zone_id, updates=dose_plan.pid_state_updates, now=now)
# Строка 246+: новый correction state только готовится в памяти
next_corr = replace(corr, needs_ec=dose_plan.needs_ec, ...)
```

**Влияние:** Возможна рассинхронизация между PID memory и шагом correction state при частичном сбое БД.

**Рекомендация:** Либо делать PID persist и `update_stage()` атомарно, либо явно принять и задокументировать этот failure mode как допустимый.

---

### BUG-2: [LOW] Whitespace-only API token проходит валидацию
**Файл:** `ae3lite/runtime/config.py` (validate())

Задокументировано в тестах (`test_ae3lite_config_validate.py:57-65`):
```python
# whitespace string is truthy — passes validate()
cfg = _config(history_logger_api_token="   ")
cfg.validate()  # НЕ бросает исключение
```

`from_env()` стрипает, но при прямой конструкции whitespace-only token проходит. При production это маловероятно (env vars через Docker), но потенциальная дыра.

---

### BUG-3: [LOW] Lease lost + task success = misleading warning
**Файл:** `ae3lite/runtime/worker.py:164-169`

Если heartbeat failит (lease_lost_event.set()) **после** успешного завершения task, логируется "task finished after lease was lost". Task уже completed и intent помечен terminal — но warning создаёт spurious алерт.

**Влияние:** Операционная путаница. Не влияет на корректность.

---

## 2. АРХИТЕКТУРНЫЕ НАБЛЮДЕНИЯ И HARDENING

### ARCH-1: Timeout mismatch Scheduler → AE → HL
```
Scheduler → AE:  timeout = 2.0 сек (services.php:56)
AE → HL:         timeout = 5.0 сек (history_logger_client.py:28)
```

На текущем ingress path это выглядит как потенциальный, но не реализующийся mismatch: `start-cycle` endpoint не ждёт ответа от HL, потому что publish в `history-logger` происходит позже уже внутри worker execution path.

**Статус:** Наблюдение, а не баг. AE `/zones/{id}/start-cycle` не публикует в HL синхронно; он только claim/create canonical task и возвращает ответ. Текущее значение `2s` выглядит достаточным, пока ingress не обрастает тяжёлой синхронной логикой.

---

### ARCH-2: IntentStatusListener использует fire-and-forget fast-path
**Файл:** `ae3lite/infrastructure/intent_status_listener.py:123-133`

`_dispatch()` запускается через `create_task()`, а ошибка callback только логируется.

Важно: это не подтверждённый production bug уровня "зона зависнет". Текущий callback делает только `worker.kick()`, а архитектурно `LISTEN/NOTIFY` уже является fast-path с обязательным polling fallback.

**Рекомендация:** Оставить как observability/hardening improvement. Если callback усложнится и начнёт писать в БД, тогда нужен retry/self-heal.

---

### ARCH-3: ScheduleDispatcher ловит только ConnectionException
**Файл:** `laravel/app/Services/AutomationScheduler/ScheduleDispatcher.php:118`

Исходная формулировка про непокрытый `RequestException` на `5xx` была неточной: без `->throw()` ответы `5xx` уже проходят через `!$response->successful()`.

Реальный остаточный риск уже: неожиданный `\Throwable` выше уровня HTTP-клиента пробросится наружу и оборвёт текущий scheduler cycle.

**Рекомендация:** Рассматривать как hardening. Добавить верхнеуровневый `catch (\Throwable)` с аккуратной классификацией в `retryable`/`failed`, если нужен fail-soft.

---

### ARCH-4: zone_workflow_state без автоочистки при crash
Если AE падает во время обработки задачи, `zone_workflow_state` остаётся в промежуточной фазе. Нет daemon'а очистки — только `startup_recovery_use_case` при перезапуске AE и ручной `DELETE FROM zone_workflow_state WHERE zone_id=X`.

**Рекомендация:** Startup recovery уже покрывает это. Добавить метрику `ae3_startup_recovery_zones_recovered` для мониторинга.

---

### ARCH-5: lock_ttl_sec < dispatch_interval_sec
```php
'scheduler_lock_ttl_sec' => 55,      // lock на 55 сек
'scheduler_dispatch_interval_sec' => 60,  // цикл каждые 60 сек
```

Lock освободится через 55с, следующий цикл через 60с — **OK**. Но если цикл запускается каждые 30с (everyThirtySeconds), второй вызов пропустится. Текущая конфигурация использует `everyMinute()` → проблемы нет.

**Рекомендация:** Добавить assertion: `lock_ttl_sec >= dispatch_interval_sec * 0.8`.

---

### ARCH-6: Окно orphaned claimed intent до stale reclaim
Если AE claim-ит `zone_automation_intent`, но падает до создания canonical `ae_task`, startup recovery этот случай не увидит, потому что он сканирует `ae_tasks`, а не intents.

При этом исходная оценка "зона блокируется на 20 минут" завышена. По текущей логике stale `claimed` intent может быть reclaimed уже через `start_cycle_claim_stale_sec` (default `180s`), а не через `hard_stale_after_sec`.

**Рекомендация:** Либо принять это окно как допустимое, либо добавить отдельный cleanup/reconcile для `claimed` intents без task.

---

### ARCH-7: hard_stale_after_sec рассчитывается динамически, но default всё ещё велик
Если AE процесс умер и не завершил task:
1. `expires_at` наступает через 600с
2. Task считается expired, но scheduler продолжает считать busy ещё 600с (до hard_stale_after_sec)
3. **Итого: зона заблокирована до 20 минут**

Для критичных schedules (полив) это много. Но startup_recovery при перезапуске AE сократит это время.

---

### ARCH-8: Отсутствие distributed tracing
`X-Trace-Id` передаётся вручную, но:
- Scheduler не всегда генерирует trace_id
- HL получает trace_id только если AE его передаёт
- Невозможно построить полный trace: Scheduler → AE → HL → MQTT → Node

---

### ARCH-9: zone_snapshot без LIMIT на overrides
**Файл:** `ae3lite/infrastructure/read_models/zone_snapshot_read_model.py`

В исходном аудите было указано, что запросу не хватает фильтра по временному окну. Это уже неактуально: фильтры по `applies_from/applies_until` в коде есть. Актуальное замечание уже: у запроса нет `LIMIT`, поэтому для зон с очень большим количеством активных override-записей возможен лишний memory pressure.

**Рекомендация:** Оценить реальный cardinality `grow_cycle_overrides`; при необходимости добавить ограничение/валидацию на уровне данных или bounded query.

---

### ARCH-10: Нет отдельной метрики именно по `schedule_busy`
`ScheduleDispatcher` действительно возвращает `reason: 'schedule_busy'`, но это не означает полное отсутствие метрик. В scheduler уже есть агрегированный dispatch counter по результатам (`success` / `retryable_failed` / `failed`).

Проблема уже более узкая: `schedule_busy` не выделяется отдельной reason-level метрикой и смешивается с прочими `retryable_failed`.

**Рекомендация:** Добавить `ae3_scheduler_dispatch_busy_total` counter.

---

## 3. ПОКРЫТИЕ ТЕСТАМИ

### Статистика
- **47 тестовых файлов**, ~11,800 строк
- **460 тестов** (все зелёные)
- **Оценка покрытия:** ~80%

### Хорошо покрыто (90%+)
| Модуль | Тесты | Строк |
|--------|-------|-------|
| correction_planner | test_ae3lite_correction_planner.py | 1,046 |
| handlers (все 8 stage) | 10 файлов | ~2,000 |
| workflow_router | test_ae3lite_workflow_router.py | 448 |
| execute_task | test_ae3lite_execute_task.py | 511 |
| worker integration | test_ae3lite_runtime_worker_integration.py | 801 |
| command_gateway | test_ae3lite_sequential_command_gateway.py | 374 |
| zone_snapshot | unit + integration | 814 |

### Пробелы (< 50% покрытия)

#### GAP-1: effective_targets_sql_utils.py — 0 тестов
8+ utility функций (to_iso, to_float, to_bool, merge_recursive, etc.) без явных unit-тестов. Тестируются только косвенно через snapshot integration tests.

#### GAP-2: Error path тестирование — минимальное
- PlannerConfigurationError → 2 теста
- TaskExecutionError recovery → 1 тест
- SnapshotBuildError → 0 тестов
- Fail-safe shutdown failure → 0 тестов (HistoryLoggerClientStub всегда возвращает success)

#### GAP-3: Repositories — 0 unit-тестов
Все 6 PG-репозиториев тестируются только через integration tests. Edge cases (NULL values, constraint violations, concurrent updates) не покрыты.

### Проблема качества тестов
Дублированный mock в `test_ae3lite_compat_start_cycle.py:52-56`:
```python
async def mark_intent_terminal(**kwargs):
    captured["marked_terminal"] = kwargs
async def mark_intent_terminal(**kwargs):  # ДУПЛИКАТ — dead code
    captured["marked_terminal"] = kwargs
```

---

## 4. ИНТЕГРАЦИЯ МЕЖДУ СЕРВИСАМИ

### Поток команд (верифицирован)
```
Laravel Scheduler
  ↓ POST /zones/{id}/start-cycle (timeout: 2s)
  ↓ Intent → zone_automation_intents (DB)
AE3 (worker claims intent)
  ↓ POST /commands (timeout: 5s, retry: 1)
History-Logger
  ↓ MQTT publish
ESP32 Node
```

### INT-1: HL retry ограничен одним transient retry
**Файл:** `ae3lite/infrastructure/clients/history_logger_client.py:31`

`max_retries=1` — одна повторная попытка.

Важно: это соответствует архитектурному инварианту проекта, где для `automation-engine -> history-logger` разрешён не более чем один transient retry, после чего система деградирует в fail-closed.

**Рекомендация:** Не менять значение без синхронного обновления архитектурной спецификации. Если одного retry недостаточно на практике, сначала пересмотреть инвариант, а не только код.

### INT-2: Нет ACK от нод
History-logger публикует команду в MQTT и считает delivery успешным (HTTP 200). Реальный ACK от ноды приходит через `command_response` topic, но:
- Если нода offline → команда потеряна при перезагрузке Mosquitto (QoS 0/1)
- AE считает задачу выполненной по legacy command status (poll loop)
- Реальный статус ноды не проверяется

### INT-3: Orphaned claimed intent до создания task
Если AE claim-ит intent, но crash-ится до создания task:
- intent остаётся в статусе `claimed`;
- startup recovery его не обработает, потому что recovery идёт по `ae_tasks`;
- повторный start-cycle начнёт проходить только после stale reclaim этого intent.

**Рекомендация:** Если окно в `~180s` неприемлемо, нужен отдельный reconcile/cleanup для `zone_automation_intents` без canonical task.

---

## 5. ПРИОРИТИЗАЦИЯ ДЕЙСТВИЙ

### Высокий приоритет (влияние на production)
1. **BUG-1:** Явно решить вопрос атомарности `PID state` vs `update_stage`
2. **INT-3 / ARCH-6:** Определить, допустимо ли окно orphaned `claimed` intent до stale reclaim
3. **ARCH-3:** Решить, нужен ли `catch (\Throwable)` в `ScheduleDispatcher` как fail-soft hardening

### Средний приоритет (улучшение надёжности)
4. **ARCH-10:** Добавить отдельную reason-level метрику для `schedule_busy`
5. **GAP-2:** Добрать error-path тесты
6. **ARCH-9:** Проверить cardinality `grow_cycle_overrides` и необходимость bounded query

### Низкий приоритет (качество кода)
7. **BUG-2:** Whitespace token validation
8. **BUG-3:** Уточнить/понизить шумный warning при `lease_lost_event`
9. **GAP-1:** Unit тесты для sql_utils
10. **ARCH-8:** Distributed tracing
