# 10_AI_DEV_GUIDES — Гайды для ИИ-разработки

Этот раздел содержит руководства для работы с ИИ-агентами над различными компонентами системы.

**Статус раздела:** операционные гайды и шаблоны задач (без дорожных карт и migration-планов — см. канонические спеки в `doc_ai/04_BACKEND_CORE/` и `doc_ai/06_DOMAIN_ZONES_RECIPES/`).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные гайды

#### [AI_ASSISTANT_DEV_GUIDE.md](AI_ASSISTANT_DEV_GUIDE.md)
**Общий гайд для ИИ-ассистентов**
- Принципы работы с ИИ
- Формат задач
- Проверка результатов

#### [GPT5_PROMPTING_GUIDE.md](GPT5_PROMPTING_GUIDE.md)
**Краткий конспект промптов для GPT-5.1 Codex Max**
- Принципы построения запросов
- Работа с инструментами и кодогенерацией
- Шаблон промпта и контроль качества
- Траблшутинг ошибок создания веток/PR

#### [HYDRO_PROMPTING_GUIDE.md](HYDRO_PROMPTING_GUIDE.md)
**Как писать промпты под hydro2.0**
- Предварительные проверки перед постановкой задачи
- Чек-листы по подсистемам (backend, Android, MQTT, инфраструктура, прошивки)
- Базовый шаблон, пошаговый алгоритм и мини-примеры
- Отдельный шаблон для поиска и диагностики багов

#### [DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md](DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md)
**Спецификация задач для ИИ-ассистентов**
- Формат задач
- Шаблоны задач
- Критерии приемки

#### [AI_TASK_TEMPLATES_AND_PATTERNS.md](AI_TASK_TEMPLATES_AND_PATTERNS.md)
**Шаблоны и паттерны задач**
- Готовые шаблоны
- Паттерны задач
- Примеры использования

### Специализированные гайды

#### [BACKEND_LARAVEL_PG_AI_GUIDE.md](BACKEND_LARAVEL_PG_AI_GUIDE.md)
**Гайд по backend разработке**
- Работа с Laravel
- Работа с PostgreSQL
- Паттерны разработки

#### [DATABASE_SCHEMA_AI_GUIDE.md](DATABASE_SCHEMA_AI_GUIDE.md)
**Гайд по схеме БД**
- Структура БД
- Миграции
- Работа с моделями

#### [MQTT_TOPICS_SPEC_AI_GUIDE.md](MQTT_TOPICS_SPEC_AI_GUIDE.md)
**Гайд по MQTT**
- Структура топиков
- Форматы сообщений
- Работа с MQTT

#### [PYTHON_MQTT_SERVICE_AI_GUIDE.md](PYTHON_MQTT_SERVICE_AI_GUIDE.md)
**Гайд по Python MQTT сервисам**
- Архитектура сервисов
- Реализация сервисов
- Интеграция

#### [OPERATOR_TASKS_FOR_AI_SPEC.md](OPERATOR_TASKS_FOR_AI_SPEC.md)
**Спецификация задач оператора для ИИ**
- Задачи оператора
- Автоматизация задач
- Интеграция с ИИ

---

## 🔗 Связанные разделы

- **[TASKS_FOR_AI_AGENTS.md](../TASKS_FOR_AI_AGENTS.md)** — общие правила работы с ИИ
- **[06_DOMAIN_ZONES_RECIPES](../06_DOMAIN_ZONES_RECIPES/)** — планировщик и доменная логика
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — Python-сервисы, AE3, API
- **[09_AI_AND_DIGITAL_TWIN](../09_AI_AND_DIGITAL_TWIN/)** — AI архитектура
- **[DEV_CONVENTIONS.md](../DEV_CONVENTIONS.md)** — конвенции разработки

---

## 🎯 С чего начать

1. **Общий гайд?** → Изучите [AI_ASSISTANT_DEV_GUIDE.md](AI_ASSISTANT_DEV_GUIDE.md)
2. **Формат задач?** → См. [DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md](DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md)
3. **Шаблоны?** → Прочитайте [AI_TASK_TEMPLATES_AND_PATTERNS.md](AI_TASK_TEMPLATES_AND_PATTERNS.md)
4. **Промпты под репозиторий?** → [HYDRO_PROMPTING_GUIDE.md](HYDRO_PROMPTING_GUIDE.md)
5. **Конкретный компонент?** → Выберите соответствующий специализированный гайд

### Владение scheduler / runtime

Каноника: `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `doc_ai/ARCHITECTURE_FLOWS.md`.

---

**См. также:** [Главный индекс документации](../INDEX.md)
