# 04_BACKEND_CORE — Backend (Laravel)

Этот раздел содержит документацию по backend-архитектуре, API, Python-сервисам и интеграциям.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: несовместимые изменения в защищённом pipeline запрещены; authority cutover завершён, прежний стек automation config не используется в runtime read-path.

Канонический документ по AE3:
- `ae3lite.md`

Канонический документ по automation/runtime authority:
- `AUTOMATION_CONFIG_AUTHORITY.md`

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

#### [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md)
**Единый authority automation/runtime-конфигов**
- Namespace map
- Documents / bundles / violations / presets
- Unified API
- Runtime read-path

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

#### [ae3lite.md](ae3lite.md)
Каноническая спецификация AE3-Lite (`DB-first`, `LISTEN/NOTIFY + fallback polling`, ручной rollout/rollback — раздел 10).

#### [AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md](AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md)
Детализирующий контракт интеграции AE3 с channel-level `level_* /event` от `storage_irrigation_node`.

#### [AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md](AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md)
Контракт дублирования в AE3 защитной логики IRR-ноды: fail-safe guards, `E-Stop`, mirror конфигов и stop-semantics.

#### [HISTORY_LOGGER_API.md](HISTORY_LOGGER_API.md)
Контракт REST API публикации команд в MQTT через history-logger.

#### [ERROR_CODE_CATALOG.md](ERROR_CODE_CATALOG.md)
Каталог кодов ошибок backend/AE3 для API и UI.

#### [END_TO_END_WORKFLOW_GUIDE.md](END_TO_END_WORKFLOW_GUIDE.md)
Сквозные сценарии и точки интеграции стека.

#### [REALTIME_UPDATES_ARCH.md](REALTIME_UPDATES_ARCH.md)
Архитектура real-time обновлений

#### [FULL_STACK_DEPLOY_DOCKER.md](FULL_STACK_DEPLOY_DOCKER.md)
Деплой полного стека через Docker (Laravel + Python-сервисы mqtt-bridge / history-logger / automation-engine)

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

Важно: при вопросах ownership scheduler/runtime использовать
`PYTHON_SERVICES_ARCH.md`,
`ae3lite.md`
и `AUTOMATION_CONFIG_AUTHORITY.md`
как приоритетные источники.

Для AE3 единственный нормативный документ в этом разделе: `ae3lite.md` (см. также `../ARCHITECTURE_FLOWS.md`).
`AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md` уточняет integration-contract и не переопределяет `ae3lite.md`.
`AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` дополняет его правилами дублирования fail-safe логики в AE3.

---

**См. также:** [Главный индекс документации](../INDEX.md)
