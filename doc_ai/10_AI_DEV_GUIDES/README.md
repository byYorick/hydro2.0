# 10_AI_DEV_GUIDES — Гайды для ИИ-разработки

Этот раздел содержит руководства для работы с ИИ-агентами над различными компонентами системы.

**Статус раздела:** MIXED (`ACTIVE` + `HISTORICAL`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

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

### Планы и rollout

#### [LARAVEL_SCHEDULER_MIGRATION_PLAN_FOR_AI.md](LARAVEL_SCHEDULER_MIGRATION_PLAN_FOR_AI.md)
**Актуальный план по scheduler migration/cutover (source of truth)**
- As-Is статус Laravel scheduler-dispatch
- Явная граница `переносим/не переносим`
- Implementation backlog и rollback artifact policy

#### [AI_AGENT_EXECUTION_PLAN_V2.md](AI_AGENT_EXECUTION_PLAN_V2.md)
**Операционный план выполнения задач ИИ-агентов**
- Последовательность этапов исполнения
- Контрольные точки и результаты

#### [AUTOMATION_LOGIC_AI_AGENT_PLAN.md](AUTOMATION_LOGIC_AI_AGENT_PLAN.md)
**План работ по automation-логике**
- Разделение ответственности scheduler/automation-engine
- Этапы внедрения и критерии готовности

#### [ACCESS_CONTROL_ENFORCE_ROLLOUT.md](ACCESS_CONTROL_ENFORCE_ROLLOUT.md)
**План rollout для access control**
- Порядок включения enforcement
- Риски и обратимость


### Исторические документы (scheduler runtime owner = Python, не использовать как source of truth)

Исторические документы по до-cutover runtime удалены из активного набора и не должны использоваться как source of truth.

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
- **[09_AI_AND_DIGITAL_TWIN](../09_AI_AND_DIGITAL_TWIN/)** — AI архитектура
- **[DEV_CONVENTIONS.md](../DEV_CONVENTIONS.md)** — конвенции разработки

---

## 🎯 С чего начать

1. **Общий гайд?** → Изучите [AI_ASSISTANT_DEV_GUIDE.md](AI_ASSISTANT_DEV_GUIDE.md)
2. **Формат задач?** → См. [DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md](DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md)
3. **Шаблоны?** → Прочитайте [AI_TASK_TEMPLATES_AND_PATTERNS.md](AI_TASK_TEMPLATES_AND_PATTERNS.md)
4. **Конкретный компонент?** → Выберите соответствующий специализированный гайд

---

## 📊 Статус документов

1. `ACTIVE`: общие гайды, шаблоны задач, актуальные migration/cutover планы.
2. `HISTORICAL`: старые stage/roadmap/ADR документы, отражающие закрытые этапы или прежнюю owner-модель runtime.
3. При конфликте по scheduler owner использовать:
`LARAVEL_SCHEDULER_MIGRATION_PLAN_FOR_AI.md` + `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`.

---

**См. также:** [Главный индекс документации](../INDEX.md)
