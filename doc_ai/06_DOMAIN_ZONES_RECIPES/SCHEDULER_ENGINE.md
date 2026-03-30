# SCHEDULER_ENGINE.md
# Планировщик автоматизации зон (Laravel) — каноника 2.0

**Статус:** планирование и dispatch расписаний выполняет **Laravel** (`automation:dispatch-schedules`); отдельного контейнера **`scheduler`** в Docker-стеке **нет**.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Назначение

- сопоставить **расписания полива/света/климата** из рецепта и фаз зоны с моментами запуска;
- создать **намерения (intents)** автоматизации в PostgreSQL;
- **разбудить** `automation-engine` только через канонический вызов `POST /zones/{id}/start-cycle`;
- отследить lifecycle задач в таблицах scheduler-dispatch (например `laravel_scheduler_active_tasks`, `zone_automation_intents`).

Исполнение workflow зоны (команды на узлы, ожидание терминальных статусов, коррекции) остаётся в **automation-engine** и **history-logger** — см. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `doc_ai/04_BACKEND_CORE/ae3lite.md`, `doc_ai/ARCHITECTURE_FLOWS.md`.

---

## 2. Поток данных (инвариант)

```
Laravel (cron / schedule:work / automation:dispatch-schedules)
  → запись intent + dispatch state в БД
  → POST /zones/{id}/start-cycle → automation-engine
  → … → history-logger → MQTT → ESP32
```

- Публикация команд в MQTT **только** через history-logger.
- HTTP-транспорт `POST /scheduler/task` и `GET /scheduler/task/{task_id}` **удалён** из runtime.

---

## 3. Операционные опоры

- Конфигурация и флаги cutover: переменные `AUTOMATION_LARAVEL_SCHEDULER_*`, синхронизация токенов с `automation-engine` (см. `doc_ai/08_SECURITY_AND_OPS/RUNBOOKS.md`, раздел про планировщик).
- Метрики dispatch: при необходимости — публичный endpoint Laravel `GET /api/system/scheduler/metrics` (см. `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`).
- UI оператора: schedule workspace и timeline строятся из канонического состояния автоматизации, а не из удалённого Python task API.

---

## 4. Правила для ИИ-агентов

1. Не описывать и не предлагать отдельный контейнер/процесс планировщика **вне Laravel** как владельца dispatch.
2. Любые изменения в расписании — через Laravel-команды, модели и политики, согласованные с `DATA_MODEL_REFERENCE.md`.
3. Не восстанавливать удалённые endpoint-ы задач планировщика в `automation-engine`.

---

**См. также:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `doc_ai/06_DOMAIN_ZONES_RECIPES/ZONE_LOGIC_FLOW.md`, `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` (вкладка планировщика зоны).
