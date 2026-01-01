# AGENTS.md
# Правила для ИИ‑агентов (Hydro 2.0, весь репозиторий)

Этот файл задаёт общие правила работы ИИ‑агентов для всего репозитория.
Если в подкаталоге есть свой `AGENTS.md`, он дополняет и уточняет эти правила.

---

## 1) Источники истины и контекст

- Архитектурная истина — в `doc_ai/SYSTEM_ARCH_FULL.md` и `doc_ai/01_SYSTEM/*`.
- Спецификации по слоям:
  - прошивки/железо: `doc_ai/02_HARDWARE_FIRMWARE`
  - MQTT/транспорт: `doc_ai/03_TRANSPORT_MQTT`
  - backend/core: `doc_ai/04_BACKEND_CORE`
  - данные/хранилища: `doc_ai/05_DATA_AND_STORAGE`
  - доменная логика: `doc_ai/06_DOMAIN_ZONES_RECIPES`
  - фронтенд: `doc_ai/07_FRONTEND`
  - AI/цифровой двойник: `doc_ai/09_AI_AND_DIGITAL_TWIN`
  - гайды для ИИ: `doc_ai/10_AI_DEV_GUIDES`

## 2) Контракты и совместимость

- Не ломать контракты: запрещены breaking‑changes в MQTT топиках/payload, форматах команд,
  схемах БД, ключевых полях, обязательных ID.
- Любые изменения должны оставаться совместимыми по всему пайплайну:
  `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.
- Если меняются API‑ответы или Inertia props — обновить соответствующий фронтенд.
- При изменениях протоколов/данных явно указывать совместимость:
  `Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.

## 3) Правила по слоям

- Команды к узлам идут только через Python/MQTT слой — не обходить scheduler.
- Laravel владеет схемой БД: любые изменения через миграции, без ручного DDL.
- При добавлении новых метрик телеметрии — обеспечить запись в `telemetry_samples`
  и `telemetry_last` (см. `doc_ai/05_DATA_AND_STORAGE`).

## 3.1) Laravel / БД / MQTT (уточнение)

- Laravel:
  - не обращаться к MQTT напрямую из Laravel, только через Python‑сервис
    (см. `doc_ai/10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md`).
  - auth/roles не менять без явной необходимости.
  - новые публичные API документировать до/вместе с кодом.
- БД (PostgreSQL):
  - все изменения через Laravel‑миграции; ручной DDL запрещён
    (см. `doc_ai/10_AI_DEV_GUIDES/DATABASE_SCHEMA_AI_GUIDE.md`).
  - новые сущности/поля сначала описывать в `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
  - не менять типы полей телеметрии без согласования всех слоёв.
  - избегать циклических FK‑зависимостей.
- MQTT:
  - формат топиков строго `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
    (см. `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`).
  - новые `message_type` или `channel` допустимы только при обновлении
    `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`,
    `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` и обработчиков Python.
  - любые изменения в топиках требуют обновления `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`,
    `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` и
    `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`.

## 4) Как формулировать задачи для ИИ

- Для постановки задач и промптов использовать:
  - `doc_ai/TASKS_FOR_AI_AGENTS.md`
  - `doc_ai/10_AI_DEV_GUIDES/DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md`
  - `doc_ai/10_AI_DEV_GUIDES/HYDRO_PROMPTING_GUIDE.md`
- В задаче всегда указывать:
  роль ассистента, контекст, цели, ограничения, входные артефакты, критерии приёмки,
  формат ответа.

## 5) Поведение ИИ

- Следовать `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` как базовому чек‑листу.
- Не придумывать архитектуру заново и не игнорировать спецификации.
