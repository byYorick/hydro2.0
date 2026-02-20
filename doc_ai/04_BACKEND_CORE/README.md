# 04_BACKEND_CORE — Backend (Laravel)

Этот раздел содержит документацию по backend-архитектуре, API, Python-сервисам и интеграциям.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

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

#### [REALTIME_UPDATES_ARCH.md](REALTIME_UPDATES_ARCH.md)
Архитектура real-time обновлений

#### [FULL_STACK_DEPLOY_DOCKER.md](FULL_STACK_DEPLOY_DOCKER.md)
Деплой полного стека через Docker

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

---

**См. также:** [Главный индекс документации](../INDEX.md)
