# Аудит и план улучшений automation-engine (ae3lite)

**Дата:** 2026-03-11
**Ветка:** ae3
**Скоуп:** Полный аудит `backend/services/automation-engine/ae3lite/`

---

## Оглавление

1. [Критичные баги](#1-критичные-баги)
2. [Логические ошибки и edge cases](#2-логические-ошибки-и-edge-cases)
3. [Мёртвый код и неиспользуемые метрики](#3-мёртвый-код-и-неиспользуемые-метрики)
4. [Пробелы в обработке ошибок](#4-пробелы-в-обработке-ошибок)
5. [Пробелы в тестовом покрытии](#5-пробелы-в-тестовом-покрытии)
6. [Пробелы в логировании и наблюдаемости](#6-пробелы-в-логировании-и-наблюдаемости)
7. [Конфигурация и hardcoded values](#7-конфигурация-и-hardcoded-values)
8. [Рефакторинг и code quality](#8-рефакторинг-и-code-quality)
9. [Приоритизированный план работ](#9-приоритизированный-план-работ)

---

## 1. Критичные баги

### 1.1 `int(x or 0) or None` — потеря ID со значением 0

**Файлы:**
- `ae3lite/api/compat_endpoints.py:114,124`
- `ae3lite/application/adapters/legacy_intent_mapper.py:32,47`

**Проблема:** Паттерн `int(intent_row.get("id") or 0) or None` при значении `id=0` вычисляется как `int(0) or None → None`. ID=0 теряется.

**Исправление:**
```python
# Было:
"active_intent_id": int(intent_row.get("id") or 0) or None

# Стало:
id_val = intent_row.get("id")
"active_intent_id": int(id_val) if id_val is not None else None
```

**Риск:** Средний. В production ID обычно > 0, но паттерн некорректен по сути и может сработать в edge cases.

---

### 1.2 `stage_retry_count` не инкрементируется в `prepare_recirc_window`

**Файл:** `ae3lite/application/handlers/prepare_recirc_window.py:56`

**Проблема:** При переходе из `prepare_recirculation_window` обратно в `prepare_recirculation_check` счётчик передаётся без инкремента:

```python
return StageOutcome(
    kind="transition",
    next_stage="prepare_recirculation_check",
    stage_retry_count=retry_count,  # ← НЕ инкрементируется
)
```

Во всех остальных handler'ах (`correction.py:475,496`, `prepare_recirc.py:47`) инкремент есть: `stage_retry_count=... + 1`.

**Последствие:** Счётчик попыток не растёт при повторных входах через окно, что может привести к бесконечным retry.

**Исправление:** `stage_retry_count=retry_count + 1`

---

### 1.3 Off-by-one в проверке `attempt > max_attempts`

**Файл:** `ae3lite/application/handlers/correction.py:178`

**Проблема:** Используется `>` вместо `>=`:
```python
if corr.attempt > corr.max_attempts:  # attempt=5, max=5 → пропускает
```

При этом в том же файле (строки 238-240) правильно используется `>=`:
```python
if corr.ec_attempt >= corr.ec_max_attempts:  # attempt=5, max=5 → срабатывает
```

**Последствие:** Коррекция выполняется на одну итерацию больше, чем настроено.

**Исправление:** `if corr.attempt >= corr.max_attempts:`

---

### 1.4 `control_mode_snapshot` — falsy-проверка вместо None-проверки

**Файл:** `ae3lite/domain/entities/automation_task.py:70-81`

**Проблема:**
```python
raw_control_mode = row.get("control_mode_snapshot") or row.get("control_mode") or "auto"
```

Если `control_mode_snapshot` явно установлен как пустая строка `""` (falsy), он будет пропущен и заменён на `control_mode`. Нужна проверка `is not None`.

---

### 1.5 Отсутствие валидации `HISTORY_LOGGER_API_TOKEN`

**Файл:** `ae3lite/runtime/config.py:47-52`

**Проблема:** Если ни один из env vars (`HISTORY_LOGGER_API_TOKEN`, `AE_API_TOKEN`, `PY_INGEST_TOKEN`, `PY_API_TOKEN`) не установлен, token будет пустой строкой. Запросы к history-logger пойдут без авторизации, что вызовет silent failures.

**Исправление:** Добавить проверку при старте runtime:
```python
if not runtime_config.history_logger_api_token:
    raise ValueError("HISTORY_LOGGER_API_TOKEN (or AE_API_TOKEN/PY_API_TOKEN) must be set")
```

---

## 2. Логические ошибки и edge cases

### 2.1 Legacy infinite sentinel для `prepare_recirculation_max_correction_attempts`

**Файл:** `ae3lite/domain/services/cycle_start_planner.py:667`

**Проблема:** Magic sentinel как default для максимума попыток коррекции в prepare_recirculation. Фактически бесконечный цикл.

**Исправление:** Заменить на разумный default (10-20) и вынести в `settings.py`.

---

### 2.2 Непредсказуемый выбор EC-компонента при отсутствии policy

**Файл:** `ae3lite/domain/services/correction_planner.py:323-356`

**Проблема:** Если `ec_component_policy` пуста или не содержит данных для текущей фазы, все компоненты (npk, calcium, magnesium, micro) получают вес 0.0 и выбор зависит от алфавитного порядка.

**Исправление:** Определить explicit default priority: `npk > calcium > magnesium > micro`.

---

### 2.3 Дозирование < 1ms округляется до 0

**Файл:** `ae3lite/domain/services/correction_planner.py:525-541`

**Проблема:** `max(0, int(dose_ml / ml_per_sec * 1000))` — при очень малых дозах результат может быть 0ms, и коррекция фактически не произойдёт.

**Исправление:** Добавить минимальный порог (например, `max(MIN_DOSE_DURATION_MS, ...)`), или логировать warning при < 10ms.

---

### 2.4 Таймаут polling команды без абсолютного deadline

**Файл:** `ae3lite/infrastructure/gateways/sequential_command_gateway.py:121-149`

**Проблема:** Цикл `while True: await asyncio.sleep(poll_interval)` без абсолютного таймаута. Если команда зависнет, polling продолжится бесконечно.

**Исправление:** Добавить абсолютный таймаут на основе `task.workflow.stage_deadline_at`.

---

### 2.5 `prepare_tolerance_by_phase` — `solution_fill` всегда выбирается первым

**Файл:** `ae3lite/domain/services/two_tank_runtime_spec.py:85-100`

**Проблема:**
```python
default_prepare_tolerance = (
    prepare_tolerance_by_phase.get("solution_fill")   # ← всегда первый
    or prepare_tolerance_by_phase.get(active_phase_key)
    or prepare_tolerance_by_phase["generic"]
)
```

Phase-specific значения для `tank_recirc` и `irrigation` не будут использованы, если `solution_fill` определён.

---

## 3. Мёртвый код и неиспользуемые метрики

### 3.1 Неиспользуемые Prometheus метрики (9 из 13)

**Файл:** `ae3lite/infrastructure/metrics.py`

| Метрика | Статус | Влияние |
|---------|--------|---------|
| `TASK_CREATED` | ❌ Мёртвая | Нет tracking создания задач |
| `STAGE_RETRY` | ❌ Мёртвая | Нет tracking retry-попыток |
| `CORRECTION_ATTEMPT` | ❌ Мёртвая | Нет tracking отдельных доз |
| `TICK_DURATION` | ❌ Мёртвая | Нет tracking времени тика |
| `TICK_ERRORS` | ❌ Мёртвая | Нет tracking ошибок тика |
| `COMMAND_DISPATCHED` | ❌ Мёртвая | Нет tracking отправки команд |
| `COMMAND_DISPATCH_DURATION` | ❌ Мёртвая | Нет tracking времени dispatch |
| `COMMAND_TERMINAL` | ❌ Мёртвая | Нет tracking терминальных статусов |
| `ACTIVE_TASKS` (Gauge) | ❌ Мёртвая | Нет tracking текущих задач |

**Работающие:** `TASK_COMPLETED`, `TASK_FAILED`, `STAGE_ENTERED`, `STAGE_DURATION`, `CORRECTION_STARTED`, `CORRECTION_COMPLETED` (4/13 метрик).

### 3.2 Мёртвые утилиты

| Файл | Статус |
|------|--------|
| `utils/retry.py` (`@retry_with_backoff`, `@simple_retry`) | ❌ Нигде не импортируется |
| `utils/zone_prioritizer.py` | ❌ Нигде не импортируется |

---

## 4. Пробелы в обработке ошибок

### 4.1 Слишком широкий `except Exception` (72+ мест)

**Основные проблемные файлы:**
- `ae3lite/runtime/worker.py:150,158,187` — heartbeat, mark intent, mark terminal
- `ae3lite/runtime/app.py:108,214,254` — callback, alert sending
- `ae3lite/api/compat_endpoints.py:51,73` — mark intent terminal

**Проблема:** Все исключения обрабатываются одинаково — логируются как warning. Системные ошибки (MemoryError), сетевые (timeout) и логические (AttributeError) неразличимы.

### 4.2 Fail-safe shutdown полностью проглатывает ошибки

**Файл:** `ae3lite/application/use_cases/execute_task.py:294-300`

**Проблема:** Если fail-safe shutdown не удался, ошибка только логируется warning, пользователь не узнает.

### 4.3 Error codes — строки, не enum

**Проблема:** Error codes разбросаны по коду как строковые литералы (`"ae3_task_execution_failed"`, `"ae3_task_create_failed"`). Нет единого реестра, dynamic generation может привести к невалидным codes.

**Файлы:**
- `execute_task.py:129,144` — `getattr(exc, "code", "ae3_task_execution_failed")`
- `reconcile_command.py:134` — `f"command_{terminal_status.strip().lower()}"` (динамическая генерация)

### 4.4 Event failures только логируются, не пробрасываются

**Файл:** `ae3lite/application/use_cases/execute_task.py:74-75,100-101,177`

`AE_TASK_STARTED`, `AE_TASK_COMPLETED`, `AE_TASK_FAILED` events — если event publishing не удался, ошибка swallowed (только warning log). Audit trail может быть неполным.

---

## 5. Пробелы в тестовом покрытии

### 5.1 Модули БЕЗ тестов

**API layer (КРИТИЧНО — нет тестов безопасности):**
- `api/compat_endpoints.py`
- `api/contracts.py`
- `api/intents.py`
- `api/rate_limit.py`
- `api/security.py`
- `api/validation.py`
- `api/responses.py`

**Handler'ы (только integration через workflow_router):**
- `handlers/clean_fill.py` — нет unit-тестов
- `handlers/solution_fill.py` — нет unit-тестов
- `handlers/startup.py` — нет unit-тестов
- `handlers/prepare_recirc.py` — нет unit-тестов
- `handlers/prepare_recirc_window.py` — нет unit-тестов
- `handlers/command.py` — нет unit-тестов
- `handlers/base.py` — нет unit-тестов

**Adapters:**
- `application/adapters/legacy_intent_mapper.py` — нет тестов

**Infrastructure:**
- `infrastructure/gateways/sequential_command_gateway.py` — нет тестов на timeouts, partial failures, race conditions

### 5.2 Имеющиеся тесты (31 файл, 189 тестов, ~8200 строк)

Лучше всего покрыто:
- `test_ae3lite_correction_planner.py` — 849 строк
- `test_ae3lite_runtime_worker_integration.py` — 586 строк
- `test_ae3lite_startup_recovery_integration.py` — 534 строк
- `test_ae3lite_zone_snapshot_read_model_integration.py` — 507 строк
- `test_ae3lite_correction_handler.py` — 411 строк

---

## 6. Пробелы в логировании и наблюдаемости

### 6.1 Handler'ы без логирования (7 из 8)

| Handler | Строки логирования | Статус |
|---------|-------------------|--------|
| `handlers/correction.py` | 8 | ⚠️ Минимум |
| `handlers/base.py` | 0 | ❌ |
| `handlers/clean_fill.py` | 0 | ❌ |
| `handlers/command.py` | 0 | ❌ |
| `handlers/prepare_recirc.py` | 0 | ❌ |
| `handlers/prepare_recirc_window.py` | 0 | ❌ |
| `handlers/solution_fill.py` | 0 | ❌ |
| `handlers/startup.py` | 0 | ❌ |

**Последствие:** В production невозможно отследить, что делает система при clean_fill, solution_fill, prepare_recirculation и прочих стадиях. Диагностика проблем крайне затруднена.

### 6.2 Повторяющийся паттерн `datetime.now(timezone.utc).replace(tzinfo=None)`

**Файлы:** `runtime/app.py:31-32`, `api/compat_endpoints.py:46,68,97` — 4+ раз.

**Исправление:** Извлечь в `utcnow_naive()` утилиту.

---

## 7. Конфигурация и hardcoded values

### 7.1 Hardcoded defaults в `cycle_start_planner.py`

**Статус:** закрыто в AE3-Lite canonical runtime. Legacy sensitivity-поля удалены из active correction contract;
дозирование опирается на process gain (`ec_gain_per_ml`, `ph_up_gain_per_ml`,
`ph_down_gain_per_ml`) и stage clamps.

Множество magic numbers без документации:
```python
"max_ec_dose_ml": ..., 50.0, 1.0, 500.0,
"max_ph_dose_ml": ..., 20.0, 0.5, 200.0,
```

### 7.2 Hardcoded status strings

Статусы (`"claimed"`, `"completed"`, `"failed"`, `"waiting_command"`, `"pending"`) разбросаны по коду строковыми литералами. Нет единого enum/frozenset.

### 7.3 `lease_ttl_sec` без верхней границы

**Файл:** `ae3lite/runtime/config.py:63`

```python
lease_ttl_sec=max(30, int(os.getenv("AE_LEASE_TTL_SEC", "300"))),
```

Нет `min(max_value, ...)`. Можно установить 99999 секунд (27+ часов).

---

## 8. Рефакторинг и code quality

### 8.1 Background tasks set может расти неограниченно

**Файл:** `ae3lite/runtime/app.py:121`

`background_tasks: set[asyncio.Task]` — tasks удаляются из set через `done` callback, но если callback выбросит исключение, task останется в set навсегда. Cleanup вызывается только при shutdown.

### 8.2 Непоследовательное именование callback-параметров

В `bind_start_cycle_route`:
- `validate_scheduler_zone_fn` (паттерн `verb_noun_fn`)
- `is_start_cycle_rate_limit_enabled_fn` (паттерн `is_noun_fn`)

### 8.3 Сложная вложенная логика в `resolve_two_tank_runtime`

**Файл:** `ae3lite/domain/services/two_tank_runtime_spec.py:38-100+`

Множество fallback путей (`isinstance → .get → isinstance → .get → default`). Сложно тестировать все комбинации.

---

## 9. Приоритизированный план работ

### Фаза 1: Критичные баги (1-2 дня)

| # | Задача | Файл | Сложность |
|---|--------|------|-----------|
| 1.1 | Исправить `int(x or 0) or None` → проверка `is not None` | `compat_endpoints.py`, `legacy_intent_mapper.py` | Тривиальная |
| 1.2 | Исправить `stage_retry_count` в `prepare_recirc_window` | `prepare_recirc_window.py:56` | Тривиальная |
| 1.3 | Исправить off-by-one `>` → `>=` в correction attempt check | `correction.py:178` | Тривиальная |
| 1.4 | Исправить `control_mode_snapshot` проверку `is not None` | `automation_task.py:70` | Тривиальная |
| 1.5 | Добавить валидацию `history_logger_api_token` при старте | `config.py` | Тривиальная |
| 1.6 | Удалить legacy infinite sentinel и оставить конечный contract cap | `cycle_start_planner.py:667` | Закрыто |

### Фаза 2: Наблюдаемость (2-3 дня)

| # | Задача | Файл | Сложность |
|---|--------|------|-----------|
| 2.1 | Подключить 9 неиспользуемых Prometheus метрик | `metrics.py`, `workflow_router.py`, `worker.py` и др. | Средняя |
| 2.2 | Добавить структурированное логирование в 7 handler'ов | `handlers/*.py` | Средняя |
| 2.3 | Извлечь `utcnow_naive()` утилиту | `utils/` | Тривиальная |

### Фаза 3: Тестовое покрытие (3-5 дней)

| # | Задача | Файл | Сложность |
|---|--------|------|-----------|
| 3.1 | Тесты для API layer (`compat_endpoints`, `security`, `rate_limit`) | `tests/` | Средняя |
| 3.2 | Unit-тесты для handler'ов (clean_fill, solution_fill, prepare_recirc) | `tests/` | Высокая |
| 3.3 | Тесты для `sequential_command_gateway` (timeouts, partial failures) | `tests/` | Средняя |
| 3.4 | Тесты для `legacy_intent_mapper` | `tests/` | Лёгкая |

### Фаза 4: Обработка ошибок (2-3 дня)

| # | Задача | Файл | Сложность |
|---|--------|------|-----------|
| 4.1 | Сузить `except Exception` в критичных местах | `worker.py`, `app.py`, `compat_endpoints.py` | Средняя |
| 4.2 | Создать `ErrorCode` enum вместо строковых литералов | `domain/errors.py` | Средняя |
| 4.3 | Создать `TaskStatus` / `IntentStatus` enum | `domain/` | Средняя |
| 4.4 | Добавить абсолютный таймаут в command polling | `sequential_command_gateway.py` | Средняя |

### Фаза 5: Рефакторинг (3-4 дня)

| # | Задача | Файл | Сложность |
|---|--------|------|-----------|
| 5.1 | Вынести hardcoded defaults из `cycle_start_planner.py` в `settings.py` | `cycle_start_planner.py`, `settings.py` | Средняя |
| 5.2 | Добавить минимальный порог дозирования (ms) | `correction_planner.py` | Лёгкая |
| 5.3 | Определить explicit default priority для EC-компонентов | `correction_planner.py` | Лёгкая |
| 5.4 | Удалить мёртвый код (`utils/retry.py`, `utils/zone_prioritizer.py`) | `utils/` | Тривиальная |
| 5.5 | Добавить `max()` ограничение для `lease_ttl_sec` | `config.py` | Тривиальная |
| 5.6 | Добавить size limit для `background_tasks` set | `app.py` | Лёгкая |

---

## Общая оценка

| Категория | Найдено проблем | Критичных | Высоких | Средних | Низких |
|-----------|----------------|-----------|---------|---------|--------|
| Баги | 6 | 3 | 2 | 1 | 0 |
| Логические ошибки | 5 | 0 | 2 | 3 | 0 |
| Мёртвый код | 11 | 0 | 1 (метрики) | 0 | 10 |
| Обработка ошибок | 4 | 0 | 1 | 3 | 0 |
| Тесты | 16 модулей | 2 (API security) | 7 | 7 | 0 |
| Логирование | 7 handler'ов | 0 | 7 | 0 | 0 |
| Конфигурация | 3 | 0 | 1 | 2 | 0 |
| Code quality | 4 | 0 | 0 | 2 | 2 |

**Общий статус:** Архитектура хорошо продумана (DI, single-writer, FSM). Основные проблемы — в операционной части: 69% метрик мёртвые, 87.5% handler'ов без логов, API layer без тестов. Критичные баги (off-by-one, retry_count, int or None) — тривиальные в исправлении, но могут влиять на поведение в production.
