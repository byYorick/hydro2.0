# 04_BACKEND_CORE — Backend (Laravel)

Этот раздел содержит документацию по backend-архитектуре, API, Python-сервисам и интеграциям.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: несовместимые изменения в защищенном pipeline запрещены; миграции AE3 выполняются через compatibility bridge (`start-cycle`, `intent-*`, legacy task_type) до cutover.

---

## 📋 Документы раздела

### Основные документы

#### [BACKEND_ARCH_FULL.md](BACKEND_ARCH_FULL.md)
**Полная архитектура backend**
- Назначение backend
- Архитектурные слои
- Основные модули
- Взаимодействие с Python-сервисом
- Интеграция с фронтендом

#### [PYTHON_SERVICES_ARCH.md](PYTHON_SERVICES_ARCH.md)
**Архитектура Python-сервисов**
- Общая архитектура
- Общая библиотека (`common/`)
- Сервисы: mqtt-bridge, history-logger, automation-engine
- Laravel scheduler-dispatch как runtime owner planning/dispatch
- Взаимодействие между сервисами

#### [API_SPEC_FRONTEND_BACKEND_FULL.md](API_SPEC_FRONTEND_BACKEND_FULL.md)
**API спецификация Frontend ↔ Backend**
- REST API эндпоинты
- WebSocket события
- Форматы запросов/ответов
- Аутентификация

#### [REST_API_REFERENCE.md](REST_API_REFERENCE.md)
**Справочник REST API**
- Полный список эндпоинтов
- Параметры запросов
- Примеры ответов

#### [TECH_STACK_LARAVEL_INERTIA_VUE3_PG.md](TECH_STACK_LARAVEL_INERTIA_VUE3_PG.md)
**Технологический стек**
- Laravel
- Inertia.js
- Vue 3
- PostgreSQL

### Специализированные документы

#### [AE3_B.md](AE3_B.md)
Целевая архитектура AE3-B (task-driven runtime, distributed single-writer, strict FSM, command outcome gate)

#### [AE3_C.md](AE3_C.md)
План чистой реализации AE3-C с нуля на 4 ИИ-агента (async task runtime, no-overlap по зонам/актуаторам, phased rollout)

#### [AE3_ARCHITECTURE.md](AE3_ARCHITECTURE.md)
Детальная архитектура AE3 (контроллеры, runtime и примеры API). Нормативные контракты на pre-coding этапе задаются через раздел compatibility в начале документа и синхронизируются с AE3-C.

#### [REALTIME_UPDATES_ARCH.md](REALTIME_UPDATES_ARCH.md)
Архитектура real-time обновлений

#### [FULL_STACK_DEPLOY_DOCKER.md](FULL_STACK_DEPLOY_DOCKER.md)
Деплой полного стека через Docker (`PARTIALLY_HISTORICAL` для legacy Python scheduler секций)

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[03_TRANSPORT_MQTT](../03_TRANSPORT_MQTT/)** — MQTT протокол
- **[05_DATA_AND_STORAGE](../05_DATA_AND_STORAGE/)** — модель данных
- **[07_FRONTEND](../07_FRONTEND/)** — фронтенд интеграция

---

## 🎯 С чего начать

1. **Архитектура backend?** → Изучите [BACKEND_ARCH_FULL.md](BACKEND_ARCH_FULL.md)
2. **Python-сервисы?** → См. [PYTHON_SERVICES_ARCH.md](PYTHON_SERVICES_ARCH.md)
3. **API разработка?** → Прочитайте [API_SPEC_FRONTEND_BACKEND_FULL.md](API_SPEC_FRONTEND_BACKEND_FULL.md)
4. **REST API?** → См. [REST_API_REFERENCE.md](REST_API_REFERENCE.md)

Важно: при вопросах ownership scheduler runtime использовать
`PYTHON_SERVICES_ARCH.md` и
`doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md`
как приоритетные источники.

Для AE3 pre-coding baseline приоритет документов:
1. `AE3_C.md` (формальные контракты и migration gates)
2. `AE3_B.md` (целевая модель и phased реализация)
3. `AE3_ARCHITECTURE.md` (детализация runtime/controller дизайна без нарушения контрактов из 1-2)

---

**См. также:** [Главный индекс документации](../INDEX.md)
