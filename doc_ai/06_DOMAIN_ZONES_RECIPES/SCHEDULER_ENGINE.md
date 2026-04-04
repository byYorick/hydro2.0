# SCHEDULER_ENGINE.md
# Планировщик автоматизации зон (Laravel) — каноника 2.0

**Статус:** планирование и dispatch расписаний выполняет **Laravel** (`automation:dispatch-schedules`); отдельного контейнера **`scheduler`** в Docker-стеке **нет**.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Назначение

- сопоставить **расписания полива/света/климата** из рецепта и фаз зоны с моментами запуска;
- создать **намерения (intents)** автоматизации в PostgreSQL;
- **разбудить** `automation-engine` HTTP-вызовом к совместимому endpoint (см. §2);
- отследить lifecycle задач в таблицах scheduler-dispatch (например `laravel_scheduler_active_tasks`, `zone_automation_intents`).

Исполнение workflow зоны (команды на узлы, ожидание терминальных статусов, коррекции) остаётся в **automation-engine** и **history-logger** — см. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `doc_ai/04_BACKEND_CORE/ae3lite.md`, `doc_ai/ARCHITECTURE_FLOWS.md`.

---

## 2. Поток данных (инвариант)

```
Laravel (cron / schedule:work / automation:dispatch-schedules)
  → запись intent + dispatch state в БД
  → POST к automation-engine (endpoint зависит от типа задачи — см. ниже)
  → … → history-logger → MQTT → ESP32
```

**Wake-up endpoint по типу задачи (фактическая реализация Laravel `ScheduleDispatcher`):**

| Тип расписания (`task_type`) | HTTP endpoint в AE | Примечание |
|------------------------------|---------------------|------------|
| `irrigation` | `POST /zones/{id}/start-irrigation` | intent/task `irrigation_start`, опционально `requested_duration_sec` из payload расписания |
| `lighting` | `POST /zones/{id}/start-lighting-tick` | только при `zones.automation_runtime='ae3'`; intent/task `lighting_tick` (см. `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH_TBD.md`, C1) |
| прочие (`climate`, `mist`, `ventilation`, …) | `POST /zones/{id}/start-cycle` | diagnostics / `cycle_start`; на зонах с **`automation_runtime='ae3'`** планировщик эти типы **не диспатчит** (остаются в плане как `non_executable_planned_task_types`) |

Для **`automation_runtime ≠ ae3`** по-прежнему используется прежняя матрица endpoint-ов (в т.ч. `start-cycle` для типов вне полива — см. код `ScheduleDispatcher`).

- Публикация команд в MQTT **только** через history-logger.
- HTTP-транспорт `POST /scheduler/task` и `GET /scheduler/task/{task_id}` **удалён** из runtime.

---

## 3. Операционные опоры

- Конфигурация и флаги cutover: переменные `AUTOMATION_LARAVEL_SCHEDULER_*`, синхронизация токенов с `automation-engine` (см. `doc_ai/08_SECURITY_AND_OPS/RUNBOOKS.md`, раздел про планировщик).
- Метрики dispatch: при необходимости — публичный endpoint Laravel `GET /api/system/scheduler/metrics` (см. `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`).
- UI оператора: schedule workspace и timeline строятся из канонического состояния автоматизации, а не из удалённого Python task API.
- Ответ `GET /api/zones/{id}/schedule-workspace` содержит `capabilities.ae3_irrigation_only_dispatch` (историческое имя: «ограниченный набор типов под автодиспатч на AE3»), `capabilities.executable_task_types` и `capabilities.non_executable_planned_task_types` — источник истины для подсказок оператору на AE3 (см. `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md` §3.5.1). На AE3 автодиспатч расписания покрывает **полив и освещение**; остальные запланированные типы перечисляются как non-executable, пока не реализован отдельный compat-path.

---

## 4. Правила для ИИ-агентов

1. Не описывать и не предлагать отдельный контейнер/процесс планировщика **вне Laravel** как владельца dispatch.
2. Любые изменения в расписании — через Laravel-команды, модели и политики, согласованные с `DATA_MODEL_REFERENCE.md`.
3. Не восстанавливать удалённые endpoint-ы задач планировщика в `automation-engine`.

---

**См. также:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `doc_ai/06_DOMAIN_ZONES_RECIPES/ZONE_LOGIC_FLOW.md`, `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` (вкладка планировщика зоны).
