# 10_AI_DEV_GUIDES — Гайды для ИИ-разработки

Этот раздел содержит руководства для работы с ИИ-агентами над различными компонентами системы.


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

#### [GPT5_PROMPTING_GUIDE.md](../../docs/10_AI_DEV_GUIDES/GPT5_PROMPTING_GUIDE.md)
**Краткий конспект промптов для GPT-5.1 Codex Max (англ. версия в `docs/10_AI_DEV_GUIDES`)**
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

#### [AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md](AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md)
**Мастер-план AE2 (эволюционное развитие automation-engine)**
- Целевая архитектура отказоустойчивого AE2
- Пошаговый roadmap для ИИ-ассистентов (куда смотреть/что делать/что на выходе)
- Модель расширяемых topology/workflow плагинов

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

Все документы имеют статус **SPEC_READY** — гайды готовы к использованию.

---

**См. также:** [Главный индекс документации](../INDEX.md)
