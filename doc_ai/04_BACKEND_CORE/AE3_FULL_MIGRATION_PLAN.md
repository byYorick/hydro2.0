# AE3_FULL_MIGRATION_PLAN.md
# План полного перехода на AE3-Lite

**Версия:** 1.0
**Дата:** 2026-03-09
**Статус:** PLAN (не реализован)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Текущее состояние

### Что уже сделано
- Python `automation-engine` — **100% AE3-Lite**, кода AE2-Lite нет вообще.
  `main.py` → `ae3lite.main.main()` → `ae3lite.runtime.serve()`.
- AE3-Lite runtime работает на зонах с `automation_runtime='ae3'`.
- Корректная 11-шаговая FSM коррекции, cross-coupled PID, correction config, process calibrations.

### Что осталось от AE2-Lite
| Место | Что осталось | Почему проблема |
|-------|-------------|----------------|
| DB: `zones.automation_runtime` | DEFAULT `'ae2'` | Новые зоны создаются на несуществующем runtime |
| DB: CHECK constraint | `IN ('ae2', 'ae3')` | Нужно убрать `'ae2'` после миграции данных |
| Laravel: `ResolvesAutomationRuntime` | fallback → `'ae2'` | При DB ошибке зона попадает в несуществующий runtime |
| Laravel: `ZoneController` | validates `in:ae2,ae3` | Разрешает создание зон с AE2 |
| Laravel: `ZoneAutomationControlModeController` | proxy → AE | AE3 не поддерживает этот endpoint |
| Laravel: `ZoneAutomationManualStepController` | proxy → AE | AE3 не поддерживает этот endpoint |
| Frontend (47 мест) | `control_mode`, `manual_step` UI | Отображает кнопки для несуществующих функций |
| Tests | default `automation_runtime='ae2'` | Тесты проверяют несуществующий путь |

---

## 1. Принципы

1. **Fail-safe порядок**: сначала данные, потом код, потом cleanup.
2. **Нет двойного rollout**: переключение зоны — однократное.
3. **AE3-Lite v2 scope** (control-mode, manual-step) — отдельный этап, **не блокирует** основную миграцию.
4. **Frontend graceful degradation** — UI должен скрывать AE2-only кнопки при `automation_runtime='ae3'`.

---

## 2. Этапы

### Этап 1 — Данные (DB migration) ★ ПЕРВЫЙ

**Задача:** Мигрировать все зоны с `'ae2'` на `'ae3'`.

**Шаги:**

1. Создать Laravel migration `2026_XX_XX_000000_migrate_zones_to_ae3_runtime`:
```php
// Предусловие: нет active ae_tasks с статусами pending|claimed|running|waiting_command
// Вся логика в одной транзакции

// 1. Изменить DEFAULT
DB::statement("ALTER TABLE zones ALTER COLUMN automation_runtime SET DEFAULT 'ae3'");

// 2. Мигрировать данные
DB::statement("UPDATE zones SET automation_runtime = 'ae3' WHERE automation_runtime = 'ae2'");

// 3. Убрать 'ae2' из CHECK constraint
DB::statement("ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check");
DB::statement("ALTER TABLE zones ADD CONSTRAINT zones_automation_runtime_check
               CHECK (automation_runtime IN ('ae3'))");
```

**Предусловие перед запуском:**
```sql
-- Убедиться, что нет активных AE2 задач (которых нет, т.к. python AE уже AE3)
SELECT COUNT(*) FROM zones WHERE automation_runtime = 'ae2';
-- Убедиться, что нет активных ae_tasks для зон на ae2
SELECT z.id, z.automation_runtime
FROM zones z
WHERE z.automation_runtime = 'ae2';
```

**Rollback:** не предусмотрен — AE2-Lite runtime удалён из Python.

---

### Этап 2 — Laravel PHP cleanup ★ ПОСЛЕ ЭТАПА 1

**Файлы для изменения:**

#### 2.1 `ResolvesAutomationRuntime.php`
```php
// было:
return 'ae2';
// ...
return $normalized !== '' ? $normalized : 'ae2';

// стало:
return 'ae3';  // fallback
// ...
return $normalized !== '' ? $normalized : 'ae3';
```

#### 2.2 `ZoneController.php`
```php
// было:
'automation_runtime' => ['sometimes', 'string', 'in:ae2,ae3'],

// стало:
'automation_runtime' => ['sometimes', 'string', 'in:ae3'],
```

#### 2.3 Удалить `ZoneAutomationControlModeController.php`
- Контроллер проксирует `GET/POST /zones/{id}/control-mode` в AE.
- AE3-Lite этот endpoint не поддерживает (ae3lite.md §1, "AE3-Lite v1 не включает").
- Удалить контроллер.
- Удалить routes в `api.php`: `GET zones/{zone}/control-mode`, `POST zones/{zone}/control-mode`.

#### 2.4 Удалить `ZoneAutomationManualStepController.php`
- Аналогично — `POST /zones/{id}/manual-step` не реализован в AE3-Lite v1.
- Удалить контроллер и route.

> **Примечание:** `ZoneRelayAutotuneController` — **оставить**. Relay-autotune запускается через
> `ZoneRelayAutotuneController` → AE, но это feature AE2-Lite. До реализации в AE3 — endpoint
> возвращает 501. Контроллер можно оставить с явным ответом "не поддерживается".

---

### Этап 3 — Frontend ★ ПАРАЛЛЕЛЬНО С ЭТАПОМ 2

**Задача:** Убрать/скрыть AE2-only UI элементы (47 мест).

#### 3.1 Определить затронутые компоненты
```
backend/laravel/resources/js/types/Automation.ts
  → control_mode, control_mode_available, allowed_manual_steps

backend/laravel/resources/js/composables/useAutomationPanel.ts
  → normalizeAutomationControlMode, normalizeAutomationManualSteps

backend/laravel/resources/js/composables/useZoneAutomationScheduler.ts
  → automationControlMode, allowedManualSteps

backend/laravel/resources/js/composables/zoneSchedulerFormatters.ts
  → manual_step_* event formatters
```

#### 3.2 Стратегия
Вариант A — **Убрать UI элементы** (рекомендован для v1 cutover):
- Удалить кнопки "Ручной шаг" и переключатель "Режим управления" из zone UI.
- Оставить только Старт цикла и просмотр состояния.
- Форматтеры событий `manual_step_*` — оставить (нужны для истории событий).

Вариант B — **Показать "недоступно"**:
- Кнопки отображаются, но disabled с tooltip "Доступно только в AE2-режиме".
- Менее инвазивно, но создаёт путаницу у пользователя.

**Рекомендован Вариант A** — зоны уже на AE3, кнопки бесполезны.

#### 3.3 Типы TypeScript
Из `Automation.ts` удалить:
- `AutomationControlMode` enum
- `AutomationManualStep` type
- поля `control_mode`, `control_mode_available`, `allowed_manual_steps` из snapshot типа

---

### Этап 4 — Тесты ★ ПАРАЛЛЕЛЬНО С ЭТАПАМИ 2-3

**Файлы с `automationRuntime: 'ae2'`:**
- `AutomationDispatchSchedulesCommandTest.php` — строки 185, 245, 340
- `AutomationScheduler/SchedulerCycleServiceTest.php` — строка 159
- `Ae3LiteSchemaTest.php` — строка 28 (проверка DEFAULT — удалить тест или инвертировать)
- `Ae3LiteRuntimeSwitchGuardTest.php` — строки 28, 54, 73, 121, 138

**Изменение:** заменить `'ae2'` → `'ae3'` во всех тестовых фабриках и fixtures.

---

### Этап 5 — AE3-Lite v2: control-mode и manual-step ★ БУДУЩИЙ

Это **отдельный проект**, не блокирует cutover. Выполняется после стабилизации v1.

**Что нужно реализовать в Python:**
```python
# ae3lite/application/use_cases/set_control_mode.py
# ae3lite/application/use_cases/execute_manual_step.py
# ae3lite/infrastructure/repositories/control_mode_repository.py
```

**API в AE3-Lite:**
- `GET /zones/{id}/control-mode` — читать из `zone_workflow_state` или нового поля
- `POST /zones/{id}/control-mode` — обновить режим (`auto` | `semi` | `manual`)
- `POST /zones/{id}/manual-step` — выполнить step (`dose_ph_up`, `dose_ph_down`, `dose_ec`, `fill`, `drain`)

**Контракт:** `zones.control_mode` (новая колонка) или в `zone_workflow_state.payload`.

Вернуть контроллеры в Laravel после реализации в AE3.

---

### Этап 6 — Relay autotune в AE3-Lite ★ БУДУЩИЙ (опционально)

AE2-Lite использовал `relay-autotune` для автоматической настройки PID.
В AE3-Lite это не реализовано и не запланировано в v1.

Опции:
- A: Реализовать как отдельный AE3 use-case (высокая сложность)
- B: Удалить feature из UI (relay-autotune заменяется ручной калибровкой через process calibrations)

---

## 3. Порядок выполнения

```
Этап 1: DB migration (данные)
    ↓
Этап 2 + Этап 3 + Этап 4 (параллельно)
    ↓
Code review + тесты
    ↓
Deploy
    ↓
Этап 5 + Этап 6 (в будущем, отдельно)
```

**Оценка по затратам:**

| Этап | Сложность | Риск | Приоритет |
|------|-----------|------|-----------|
| 1 — DB migration | Низкая | Средний (данные) | P0 |
| 2 — Laravel PHP cleanup | Низкая | Низкий | P0 |
| 3 — Frontend cleanup | Средняя | Низкий | P0 |
| 4 — Тесты | Низкая | Низкий | P0 |
| 5 — AE3 control-mode/manual-step | Высокая | Средний | P2 |
| 6 — Relay autotune | Высокая | Высокий | P3 |

---

## 4. Критерии приёмки

### После этапов 1-4:
- [ ] `SELECT COUNT(*) FROM zones WHERE automation_runtime != 'ae3'` = 0
- [ ] `zones.automation_runtime` DEFAULT = `'ae3'`, CHECK constraint только `'ae3'`
- [ ] `ZoneController` не принимает `automation_runtime='ae2'` (400)
- [ ] `ResolvesAutomationRuntime` fallback = `'ae3'`
- [ ] `ZoneAutomationControlModeController` удалён, routes удалены
- [ ] `ZoneAutomationManualStepController` удалён, routes удалены
- [ ] Frontend не отображает кнопки "Ручной шаг" и "Режим управления"
- [ ] Все тесты используют `'ae3'` как default runtime
- [ ] Все Laravel тесты зелёные
- [ ] Все AE3-Lite pytest тесты зелёные

---

## 5. Что удаляется навсегда

После завершения этапов 1-4 следующий код становится dead code и удаляется:
- `ZoneAutomationControlModeController.php`
- `ZoneAutomationManualStepController.php`
- Валидация `'ae2'` в `ZoneController`
- Fallback `'ae2'` в `ResolvesAutomationRuntime`
- Frontend: `AutomationControlMode` type, `normalizeAutomationControlMode()`
- Frontend: `AutomationManualStep` type, `normalizeAutomationManualSteps()`
- Frontend компоненты управления режимом и ручным шагом (если Вариант A)

---

## 6. Связанные документы

- `ae3lite.md` — канонический spec AE3-Lite (§1 — что не включено в v1)
- `AE3LITE_ROLLOUT_ROLLBACK_RUNBOOK.md` — процедура ручного переключения зоны
- `CORRECTION_CYCLE_SPEC.md` — FSM коррекции pH/EC
- `PYTHON_SERVICES_ARCH.md` — общая архитектура сервисов
