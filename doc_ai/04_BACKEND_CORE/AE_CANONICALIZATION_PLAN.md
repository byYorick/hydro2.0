# AE Canonicalization Plan — Полная канонизация Automation Engine

**Версия:** 1.0
**Дата:** 2026-03-14
**Ветка:** ae3
**Статус:** ACTIVE PLAN — для выполнения ИИ-агентами
**Спецификация:** `doc_ai/04_BACKEND_CORE/ae3lite.md` (source of truth)

---

## 0. Контракт агента

Агент исполняет этот план **строго последовательно**.

Правила:
1. Каждая фаза начинается только после зелёного теста предыдущей
2. Агент читает все упомянутые файлы перед правкой
3. После каждой фазы — запуск указанных тестов
4. Запрещено расширять scope фазы без изменения этого документа
5. При блокере — зафиксировать `BLOCKER:` и остановиться

Команды запуска тестов:
```bash
# Python AE
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q

# PHP Laravel
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test

# Конкретный файл
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q test_ae3lite_XYZ.py
```

---

## Инвентарь: что найдено и что нужно сделать

### Мёртвый код (confirmed unused — ни один import не найден)

| Файл | Строк | Причина удаления |
|------|-------|-----------------|
| `utils/adaptive_pid.py` | 464 | Deprecated AdaptivePid/RelayAutotuner, не используется в production |
| `config/settings.py` | 189 | Legacy от ae2 — ae3lite использует `ae3lite/runtime/config.py` |
| `config/scheduler_task_mapping.py` | 154 | Legacy ae2 command routing — ae3lite использует `CycleStartPlanner` + DB `command_plans` |
| `config/__init__.py` | ~1 | Станет пустой директорией после удаления |

Верификация: `grep -r "from config" ae3lite/` и `grep -r "adaptive_pid" .` — оба дают 0 результатов.

### Дублирующиеся тест-файлы (10 файлов → 5)

Исторически создавались по двум конвенциям именования:
- `test_ae3lite_handler_X.py` (новая конвенция — `handler_` префикс)
- `test_ae3lite_X_handler.py` (старая конвенция — `_handler` суффикс)

| Старый файл | Новый файл | Действие |
|-------------|------------|----------|
| `test_ae3lite_clean_fill_handler.py` | `test_ae3lite_handler_clean_fill.py` | Прочитать оба, объединить, удалить старый |
| `test_ae3lite_command_handler.py` | `test_ae3lite_handler_command.py` | Прочитать оба, объединить, удалить старый |
| `test_ae3lite_startup_handler.py` | `test_ae3lite_handler_startup.py` | Прочитать оба, объединить, удалить старый |
| `test_ae3lite_solution_fill_handler.py` | `test_ae3lite_handler_solution_fill.py` | Оба модифицированы в git — объединить |
| `test_ae3lite_prepare_recirc_handler.py` + `test_ae3lite_prepare_recirc_check_handler.py` + `test_ae3lite_prepare_recirc_window_handler.py` | `test_ae3lite_handler_prepare_recirc_window.py` | Четыре файла → один, объединить уникальные тесты |

### In-progress изменения (unstaged/untracked на ветке ae3)

Текущие незакоммиченные изменения требуют завершения и тестирования:

| Файл | Статус | Суть изменения |
|------|--------|---------------|
| `ae3lite/application/handlers/solution_fill.py` | Modified | Pump calibration checks |
| `ae3lite/application/use_cases/guard_solution_tank_startup_reset.py` | **NEW** | Гарантия безопасного состояния solution tank при startup |
| `ae3lite/api/compat_endpoints.py` | Modified | Интеграция solution tank guard |
| `ae3lite/application/use_cases/get_zone_automation_state.py` | Modified | Обновлённый state response |
| `ae3lite/domain/services/correction_planner.py` | Modified | Pump calibration validation |
| `ae3lite/runtime/app.py` | Modified | Wiring новых use cases |
| `ae3lite/runtime/bootstrap.py` | Modified | DI для новых use cases |
| `test_ae3lite_get_zone_automation_state.py` | **NEW** | Тесты нового state use case |
| `test_ae3lite_solution_tank_startup_guard.py` | **NEW** | Тесты startup guard |
| `backend/laravel/app/Services/AutomationScheduler/ScheduleDispatcher.php` | Modified | Scheduler dispatcher изменения |

### Отсутствующие DB constraints (per ae3lite.md §6)

| Таблица | Constraint | Статус |
|---------|-----------|--------|
| `ae_tasks` | Не более одной активной task на `zone_id` | MISSING |
| `ae_tasks` | Уникальность `idempotency_key` в scope | MISSING |
| `zone_workflow_state` | `version BIGINT NOT NULL DEFAULT 0` для CAS | MISSING |
| `zones` | `automation_runtime TEXT NOT NULL DEFAULT 'ae2' CHECK (automation_runtime IN ('ae2','ae3'))` | Verify |

### Архитектурный долг: intents.py

`ae3lite/api/intents.py` содержит сырые SQL-запросы управления lifecycle intent через функции высшего порядка (`fetch_fn`, `execute_fn`). Это нарушает паттерн Repository, используемый в остальном коде. Подлежит рефакторингу в фазе 5.

---

## Фаза 1: Верификация текущего состояния тестов

**ПЕРВЫМ ДЕЛОМ** — убедиться что базовые тесты зелёные.

### Шаги

1. Запустить полный suite:
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
```

2. Если тесты падают — прочитать ошибки, исправить, убедиться в зелёном состоянии.

3. Записать количество пройденных тестов (baseline).

4. PHP тесты:
```bash
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=AutomationScheduler
```

### Критерии завершения фазы 1
- ✅ Python pytest: 0 failures, 0 errors
- ✅ PHP artisan test (AutomationScheduler): 0 failures
- ✅ Зафиксировано baseline кол-во тестов

---

## Фаза 2: Удаление мёртвого кода

### Шаги

#### 2.1 Удалить utils/adaptive_pid.py

Перед удалением выполнить финальную проверку:
```bash
grep -r "adaptive_pid\|AdaptivePid\|RelayAutotuner" \
    backend/services/automation-engine/ \
    --include="*.py" \
    --exclude-dir="__pycache__"
```
Если вывод пустой — удалить:
```
backend/services/automation-engine/utils/adaptive_pid.py
```

#### 2.2 Удалить config/ директорию

Проверка отсутствия импортов:
```bash
grep -r "from config\|import config" \
    backend/services/automation-engine/ae3lite/ \
    --include="*.py"
```
Если вывод пустой — удалить:
```
backend/services/automation-engine/config/settings.py
backend/services/automation-engine/config/scheduler_task_mapping.py
backend/services/automation-engine/config/__init__.py
```

#### 2.3 Запустить тесты после удаления
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
```
Кол-во тестов должно остаться таким же как в baseline.

### Критерии завершения фазы 2
- ✅ Файлы удалены
- ✅ `grep -r "adaptive_pid\|from config"` возвращает 0 результатов в ae3lite
- ✅ pytest: кол-во тестов = baseline, 0 failures

---

## Фаза 3: Консолидация дублирующихся тестов

Цель: устранить дублирование naming convention, каждый handler — один файл тестов.

**Правило именования (каноническое):** `test_ae3lite_handler_{handler_name}.py`

### Шаги для каждой пары

#### Для каждой пары:
1. Прочитать оба файла полностью
2. Определить какой содержит больше / более актуальные тесты
3. В НОВЫЙ (canonical) файл перенести все уникальные тесты из СТАРОГО
4. Удалить СТАРЫЙ файл
5. Запустить конкретный тест-файл: `pytest -x -q test_ae3lite_handler_X.py`

#### 3.1 clean_fill handler
- Читать: `test_ae3lite_clean_fill_handler.py` (старый) + `test_ae3lite_handler_clean_fill.py` (новый)
- Объединить в: `test_ae3lite_handler_clean_fill.py`
- Удалить: `test_ae3lite_clean_fill_handler.py`

#### 3.2 command handler
- Читать: `test_ae3lite_command_handler.py` (старый) + `test_ae3lite_handler_command.py` (новый)
- Объединить в: `test_ae3lite_handler_command.py`
- Удалить: `test_ae3lite_command_handler.py`

#### 3.3 startup handler
- Читать: `test_ae3lite_startup_handler.py` (старый) + `test_ae3lite_handler_startup.py` (новый)
- Объединить в: `test_ae3lite_handler_startup.py`
- Удалить: `test_ae3lite_startup_handler.py`

#### 3.4 solution_fill handler
- Читать: `test_ae3lite_solution_fill_handler.py` + `test_ae3lite_handler_solution_fill.py` (оба modified)
- Объединить в: `test_ae3lite_handler_solution_fill.py`
- Удалить: `test_ae3lite_solution_fill_handler.py`

#### 3.5 prepare_recirc handlers (4 файла → 2)
Это РАЗНЫЕ handlers:
- `prepare_recirc_check` — проверяет таргеты при активной рециркуляции
- `prepare_recirc_window` — управляет timeout окном рециркуляции

Шаги:
- Читать: `test_ae3lite_prepare_recirc_handler.py` + `test_ae3lite_prepare_recirc_check_handler.py`
  → объединить в `test_ae3lite_handler_prepare_recirc_check.py` (NEW name)
- Читать: `test_ae3lite_prepare_recirc_window_handler.py` + `test_ae3lite_handler_prepare_recirc_window.py`
  → объединить в `test_ae3lite_handler_prepare_recirc_window.py`
- Удалить: `test_ae3lite_prepare_recirc_handler.py`, `test_ae3lite_prepare_recirc_check_handler.py`, `test_ae3lite_prepare_recirc_window_handler.py`

### Финальный запуск после фазы 3
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
```

### Критерии завершения фазы 3
- ✅ Нет файлов `test_ae3lite_*_handler.py` (кроме интеграционных: `test_ae3lite_correction_handler.py`)
- ✅ Все handler тесты живут в `test_ae3lite_handler_*.py`
- ✅ Кол-во тестов ≥ baseline (тесты добавились за счёт объединения, не потерялись)
- ✅ pytest: 0 failures

---

## Фаза 4: Завершение in-progress изменений

### Контекст

На ветке ae3 есть незакоммиченные изменения. Их нужно привести к завершённому состоянию.

### Шаги

#### 4.1 Прочитать все modified файлы

Обязательно прочитать (перед любой правкой):
- `ae3lite/application/handlers/solution_fill.py`
- `ae3lite/application/use_cases/guard_solution_tank_startup_reset.py`
- `ae3lite/api/compat_endpoints.py`
- `ae3lite/application/use_cases/get_zone_automation_state.py`
- `ae3lite/domain/services/correction_planner.py`
- `ae3lite/runtime/app.py`
- `ae3lite/runtime/bootstrap.py`
- `test_ae3lite_get_zone_automation_state.py`
- `test_ae3lite_solution_tank_startup_guard.py`
- `backend/laravel/app/Services/AutomationScheduler/ScheduleDispatcher.php`

#### 4.2 Верифицировать pump calibration в solution_fill

`solution_fill.py` должен:
- Проверять наличие pump calibration перед дозированием
- Логировать warning при отсутствии калибровки
- Блокировать дозирование если `ml_per_sec` вне диапазона [0.01, 100.0]
- Тесты: `test_ae3lite_handler_solution_fill.py` — запустить отдельно

#### 4.3 Верифицировать guard_solution_tank_startup_reset

Новый use case должен:
- Проверять уровень solution tank перед startup
- Если tank не empty при startup — сбрасывать zone_workflow_state
- Работать как non-blocking check в compat_endpoints.py (ошибки игнорируются с warning)
- Тесты: `test_ae3lite_solution_tank_startup_guard.py` — запустить отдельно

#### 4.4 Верифицировать get_zone_automation_state

Изменения должны:
- Включать информацию о solution tank guard в response
- Тесты: `test_ae3lite_get_zone_automation_state.py` — запустить отдельно

#### 4.5 Верифицировать ScheduleDispatcher.php (Laravel)

Прочитать файл и тест. Убедиться что:
- dispatch логика не сломана
- Тест `ScheduleDispatcherTest.php` проходит
```bash
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan test tests/Feature/AutomationScheduler/ScheduleDispatcherTest.php
```

#### 4.6 Исправить найденные проблемы

Если что-то из вышеперечисленного не завершено или тесты падают — завершить реализацию.

### Критерии завершения фазы 4
- ✅ `test_ae3lite_handler_solution_fill.py`: 0 failures
- ✅ `test_ae3lite_solution_tank_startup_guard.py`: 0 failures
- ✅ `test_ae3lite_get_zone_automation_state.py`: 0 failures
- ✅ `ScheduleDispatcherTest.php`: 0 failures
- ✅ Полный `pytest -x -q`: 0 failures

---

## Фаза 5: DB Constraints (Laravel Migration)

### Контекст

Согласно `ae3lite.md` §6, следующие constraints отсутствуют или требуют верификации.

### Шаги

#### 5.1 Проверить текущее состояние схемы

```bash
docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "\d ae_tasks"

docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "\d zone_workflow_state"

docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "\d zones" | grep automation_runtime
```

#### 5.2 Создать Laravel миграцию

Создать файл:
```
backend/laravel/database/migrations/2026_03_14_000001_add_ae3_canonical_constraints.php
```

Миграция должна добавить (только если отсутствуют через `IF NOT EXISTS`):

**ae_tasks:**
```sql
-- Partial unique index: не более одной активной task на zone
CREATE UNIQUE INDEX IF NOT EXISTS uq_ae_tasks_one_active_per_zone
    ON ae_tasks (zone_id)
    WHERE status NOT IN ('completed', 'failed', 'cancelled');

-- Уникальность idempotency_key (глобальная, для предотвращения cross-zone конфликтов)
-- ВНИМАНИЕ: проверить есть ли уже constraint в схеме перед добавлением
```

**zone_workflow_state:**
```sql
-- version column для CAS updates
ALTER TABLE zone_workflow_state
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
```

**zones:**
```sql
-- automation_runtime rollout flag
ALTER TABLE zones
    ADD COLUMN IF NOT EXISTS automation_runtime TEXT NOT NULL DEFAULT 'ae2';

ALTER TABLE zones
    DROP CONSTRAINT IF EXISTS chk_zones_automation_runtime;

ALTER TABLE zones
    ADD CONSTRAINT chk_zones_automation_runtime
    CHECK (automation_runtime IN ('ae2', 'ae3'));
```

#### 5.3 Применить миграцию
```bash
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan migrate
```

#### 5.4 Верифицировать constraints
```bash
docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "\d ae_tasks" | grep -i unique

docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "\d zone_workflow_state" | grep version
```

#### 5.5 Запустить тесты после миграции
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test
```

### Критерии завершения фазы 5
- ✅ Partial unique index на `ae_tasks` для одной активной task на zone
- ✅ `version` column в `zone_workflow_state`
- ✅ `automation_runtime` column в `zones` с CHECK constraint
- ✅ `make migrate` не падает
- ✅ Все тесты зелёные

---

## Фаза 6: Рефакторинг intents.py → ZoneIntentRepository

### Контекст

`ae3lite/api/intents.py` содержит сырые SQL-запросы с паттерном functional injection (`fetch_fn`, `execute_fn`). Это нарушает архитектуру repository layer.

Текущая цепочка:
```
app.py → bootstrap.py → worker.py / compat_endpoints.py
             ↓ callables
         intents.py (claim/mark_running/mark_terminal)
```

Целевая цепочка:
```
app.py → bootstrap.py → worker.py / compat_endpoints.py
             ↓ repository
         PgZoneIntentRepository (infrastructure layer)
```

### Шаги

#### 6.1 Прочитать все связанные файлы

- `ae3lite/api/intents.py` — текущая реализация
- `ae3lite/runtime/bootstrap.py` — wiring callables
- `ae3lite/runtime/app.py` — как callables используются
- `ae3lite/api/compat_endpoints.py` — использование `claim_start_cycle_intent_fn`
- `ae3lite/runtime/worker.py` — использование `mark_intent_running_fn`, `mark_intent_terminal_fn`
- `ae3lite/infrastructure/repositories/` — посмотреть существующие паттерны

#### 6.2 Создать ZoneIntentRepository

Файл: `ae3lite/infrastructure/repositories/zone_intent_repository.py`

Интерфейс:
```python
class PgZoneIntentRepository:
    async def claim_start_cycle(
        self,
        zone_id: int,
        req: StartCycleRequest,
        now: datetime,
        *,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]: ...

    async def mark_running(
        self,
        intent_id: int,
        now: datetime,
    ) -> None: ...

    async def mark_terminal(
        self,
        intent_id: int,
        now: datetime,
        *,
        success: bool,
        error_code: str | None,
        error_message: str | None,
    ) -> None: ...
```

SQL логика — перенести из `intents.py` без изменений.

#### 6.3 Обновить bootstrap.py

- Инстанцировать `PgZoneIntentRepository` в `build_ae3_runtime_bundle()`
- Убрать `mark_intent_running_fn` и `mark_intent_terminal_fn` из параметров функции
- Передать `zone_intent_repository` напрямую в worker и compat_endpoints

#### 6.4 Обновить worker.py

- Принимать `zone_intent_repository: PgZoneIntentRepository` вместо callables
- Вызывать `await zone_intent_repository.mark_running(...)` и `.mark_terminal(...)`

#### 6.5 Обновить compat_endpoints.py

- Принимать `zone_intent_repository: PgZoneIntentRepository` вместо `claim_start_cycle_intent_fn`
- Вызывать `await zone_intent_repository.claim_start_cycle(...)`
- Убрать `mark_intent_terminal_fn` из параметров (использовать repository)

#### 6.6 Обновить app.py

- Убрать callable closures для `mark_intent_running_fn`, `mark_intent_terminal_fn`
- Передать repository

#### 6.7 Удалить или оставить intents.py как thin facade

После рефакторинга `ae3lite/api/intents.py` можно:
- Либо удалить (если ни один test не импортирует напрямую)
- Либо оставить как deprecated thin wrapper с `DeprecationWarning`

Проверить: `grep -r "from ae3lite.api.intents\|from ae3lite.api import intents" .`

#### 6.8 Обновить инициализацию repositories __init__.py

Добавить `PgZoneIntentRepository` в `ae3lite/infrastructure/repositories/__init__.py`.

#### 6.9 Написать тесты

Создать: `test_ae3lite_zone_intent_repository.py`

Тесты:
- `test_claim_start_cycle_success` — успешный claim нового intent
- `test_claim_start_cycle_deduplicated` — повторный запрос с тем же idempotency_key
- `test_claim_start_cycle_zone_busy` — зона занята
- `test_mark_running` — переход в running
- `test_mark_terminal_success` — успешное завершение
- `test_mark_terminal_failure` — ошибочное завершение

#### 6.10 Запустить полный suite
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
```

### Критерии завершения фазы 6
- ✅ `PgZoneIntentRepository` создан в infrastructure/repositories/
- ✅ `bootstrap.py` не передаёт callables для intent lifecycle
- ✅ `worker.py` использует repository, не callables
- ✅ `compat_endpoints.py` использует repository, не callables
- ✅ `intents.py` удалён или оставлен как documented thin facade
- ✅ `test_ae3lite_zone_intent_repository.py`: 0 failures
- ✅ Полный pytest: 0 failures

---

## Фаза 7: Финальная верификация

### Шаги

#### 7.1 Полный Python suite
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q
```
Ожидается: все тесты зелёные, кол-во ≥ baseline фазы 1.

#### 7.2 Полный PHP suite
```bash
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test
```

#### 7.3 Protocol check
```bash
make protocol-check
```

#### 7.4 Проверка отсутствия мёртвого кода
```bash
# Нет import adaptive_pid
grep -r "adaptive_pid" backend/services/automation-engine/ --include="*.py"

# Нет import config.settings
grep -r "from config\." backend/services/automation-engine/ --include="*.py"

# Нет дублирующихся тест-файлов
ls backend/services/automation-engine/test_ae3lite_*_handler.py 2>/dev/null | wc -l
# Должно быть 0 (кроме correction_handler.py если он не дубль)
```

#### 7.5 Проверка DB constraints
```bash
docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'ae_tasks' AND indexname LIKE '%active%';

    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'zone_workflow_state' AND column_name = 'version';

    SELECT column_name, column_default, constraint_name
    FROM information_schema.columns c
    LEFT JOIN information_schema.constraint_column_usage u
      ON c.column_name = u.column_name AND c.table_name = u.table_name
    WHERE c.table_name = 'zones' AND c.column_name = 'automation_runtime';
  "
```

#### 7.6 Smoke test вручную
```bash
# 1. Убедиться что стек запущен
make up

# 2. Получить auth token
curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}' | jq .token

# 3. Проверить state зоны
curl -s http://localhost:9405/zones/447/state \
  -H "Authorization: Bearer dev-token-12345" | jq .

# 4. Проверить health
curl -s http://localhost:9405/health | jq .
```

### Критерии завершения фазы 7 (Definition of Done)
- ✅ Python: 0 failures, 0 errors, кол-во тестов ≥ baseline
- ✅ PHP: 0 failures
- ✅ Нет мёртвого кода (проверки из 7.4 дают пустой вывод)
- ✅ DB constraints верифицированы (проверка 7.5)
- ✅ Smoke test: AE отвечает, зоны отображаются
- ✅ `ScheduleDispatcher.php` тест зелёный

---

## Итоговая структура после канонизации

```
backend/services/automation-engine/
├── ae3lite/                    # Единственная production реализация
│   ├── api/
│   │   ├── compat_endpoints.py   # Использует ZoneIntentRepository (не callables)
│   │   ├── internal_endpoints.py
│   │   ├── contracts.py
│   │   ├── validation.py
│   │   ├── security.py
│   │   ├── rate_limit.py
│   │   └── responses.py
│   │   # intents.py УДАЛЁН или thin facade с DeprecationWarning
│   ├── application/
│   │   ├── handlers/
│   │   │   ├── base.py
│   │   │   ├── startup.py
│   │   │   ├── clean_fill.py
│   │   │   ├── solution_fill.py  # + pump calibration
│   │   │   ├── prepare_recirc.py
│   │   │   ├── prepare_recirc_window.py
│   │   │   ├── command.py
│   │   │   └── correction.py
│   │   ├── use_cases/
│   │   │   ├── create_task_from_intent.py
│   │   │   ├── claim_next_task.py
│   │   │   ├── execute_task.py
│   │   │   ├── workflow_router.py
│   │   │   ├── publish_planned_command.py
│   │   │   ├── reconcile_command.py
│   │   │   ├── finalize_task.py
│   │   │   ├── startup_recovery.py
│   │   │   ├── get_zone_automation_state.py  # обновлён
│   │   │   ├── get_zone_control_state.py
│   │   │   └── guard_solution_tank_startup_reset.py  # НОВЫЙ
│   │   ├── adapters/
│   │   │   └── legacy_intent_mapper.py
│   │   └── dto/
│   ├── domain/
│   │   ├── entities/
│   │   ├── services/
│   │   │   ├── correction_planner.py  # + pump calibration validation
│   │   │   ├── cycle_start_planner.py
│   │   │   ├── two_tank_runtime_spec.py
│   │   │   ├── topology_registry.py
│   │   │   └── phase_utils.py
│   │   └── errors.py
│   ├── infrastructure/
│   │   ├── repositories/
│   │   │   ├── automation_task_repository.py
│   │   │   ├── zone_lease_repository.py
│   │   │   ├── zone_workflow_repository.py
│   │   │   ├── pid_state_repository.py
│   │   │   ├── zone_alert_repository.py
│   │   │   ├── zone_alert_write_repository.py
│   │   │   ├── zone_correction_config_repository.py
│   │   │   ├── ae_command_repository.py
│   │   │   └── zone_intent_repository.py  # НОВЫЙ (из intents.py)
│   │   ├── read_models/
│   │   ├── gateways/
│   │   ├── clients/
│   │   ├── intent_status_listener.py
│   │   └── metrics.py
│   └── runtime/
│       ├── app.py      # без callable closures для intent
│       ├── worker.py   # использует ZoneIntentRepository
│       ├── bootstrap.py  # без functional injection
│       └── config.py
├── utils/
│   ├── zone_prioritizer.py
│   ├── logging_context.py
│   └── retry.py
│   # adaptive_pid.py УДАЛЁН
# config/ ДИРЕКТОРИЯ УДАЛЕНА
└── test_ae3lite_*.py   # канонические имена: test_ae3lite_handler_X.py
```

---

## Контрольный список для агента

После каждой фазы отметить:

- [ ] Фаза 1: Baseline тесты зелёные
- [ ] Фаза 2: Мёртвый код удалён, тесты зелёные
- [ ] Фаза 3: Дублирующиеся тесты объединены, кол-во ≥ baseline
- [ ] Фаза 4: In-progress изменения завершены, новые тесты зелёные
- [ ] Фаза 5: DB constraints применены через миграцию
- [ ] Фаза 6: intents.py рефакторинг в ZoneIntentRepository
- [ ] Фаза 7: Финальная верификация — всё зелёное

---

## Ссылки на ключевые файлы

| Документ | Путь |
|----------|------|
| Canonical spec (AE3-Lite) | `doc_ai/04_BACKEND_CORE/ae3lite.md` |
| Laravel scheduler as-built | `doc_ai/04_BACKEND_CORE/LARAVEL_SCHEDULER_REFACTORING.md` |
| Scheduler audit | `doc_ai/04_BACKEND_CORE/AE_SCHEDULER_AUDIT.md` |
| System architecture | `doc_ai/SYSTEM_ARCH_FULL.md` |
| Dev conventions | `doc_ai/DEV_CONVENTIONS.md` |
