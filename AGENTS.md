# AGENTS.md
# Правила для ИИ‑агентов (Hydro 2.0, весь репозиторий)

**Дата обновления:** 2026-02-14  
**Версия:** 2.0  
**Статус:** Основной документ правил для ИИ‑агентов

## Цель

Зафиксировать единые правила для ИИ‑агентов, чтобы изменения оставались совместимыми,
архитектурно корректными и воспроизводимыми.

## Контекст

Этот файл задаёт общие правила для всего репозитория. Если в подкаталоге есть свой
`AGENTS.md`, он дополняет и уточняет эти правила.

## Быстрая сводка (обязательный минимум)

- Общаться с пользователем только на русском языке.
- Перед работой открыть минимум: `doc_ai/INDEX.md`, `doc_ai/SYSTEM_ARCH_FULL.md`,
  `doc_ai/ARCHITECTURE_FLOWS.md`, `doc_ai/DEV_CONVENTIONS.md`.
- `doc_ai/` — source of truth; `docs/` вручную не редактировать.
- Команды к узлам не публикуются напрямую из scheduler/automation/Laravel:
  единая точка публикации в MQTT — `history-logger`.
- Базовый поток команд: `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.
- Не ломать защищённый пайплайн `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.
- Любые изменения протокола/данных сопровождать обновлением спецификаций и строкой:
  `Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.
- Разработка backend и сервисов — внутри Docker; изменения БД — только через Laravel-миграции.

## Связанные документы

- `doc_ai/DEV_CONVENTIONS.md` — общие конвенции разработки и оформления документации.
- `doc_ai/SYSTEM_ARCH_FULL.md` — архитектурная истина.
- `doc_ai/ARCHITECTURE_FLOWS.md` — визуализация ключевых потоков и пайплайнов.
- `doc_ai/TASKS_FOR_AI_AGENTS.md` — правила постановки задач для ИИ.
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — контракт REST API публикации команд.
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — state machine циклов коррекции.
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets.
- `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` — базовый гайд поведения ИИ.
- `doc_ai/10_AI_DEV_GUIDES/DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md` — спецификация задач.
- `doc_ai/10_AI_DEV_GUIDES/HYDRO_PROMPTING_GUIDE.md` — правила формулирования промптов.

---

## 0) Приоритет правил и разрешение конфликтов

- Приоритет (от общего к частному): корневой `AGENTS.md` -> спецификации слоя -> локальный `AGENTS.md` -> гайды для ИИ.
- Локальные правила могут уточнять базовые, но не могут противоречить спецификациям слоя.
- При конфликте или сомнении следовать более строгому требованию и запросить уточнение.

## 1) Источники истины и контекст

- Архитектурная истина — в `doc_ai/SYSTEM_ARCH_FULL.md` и `doc_ai/01_SYSTEM/*`.
- Документация в `doc_ai/` — источник истины (source of truth), `docs/` — зеркало без ручных правок.
- Спецификации по слоям:
  - прошивки/железо: `doc_ai/02_HARDWARE_FIRMWARE`
  - MQTT/транспорт: `doc_ai/03_TRANSPORT_MQTT`
  - бэкенд/core: `doc_ai/04_BACKEND_CORE`
  - данные/хранилища: `doc_ai/05_DATA_AND_STORAGE`
  - доменная логика: `doc_ai/06_DOMAIN_ZONES_RECIPES`
  - фронтенд: `doc_ai/07_FRONTEND`
  - ИИ/цифровой двойник: `doc_ai/09_AI_AND_DIGITAL_TWIN`
  - гайды для ИИ: `doc_ai/10_AI_DEV_GUIDES`

## 1.1) Обязательный минимум перед работой

- Проверить наличие локального `AGENTS.md` в подкаталоге задачи.
- Открыть 2-3 ключевых документа своего слоя из списка выше.

## 1.2) Среда разработки

- Backend/Laravel, Python-сервисы, БД и e2e запускать в Docker; команды выполнять внутри контейнеров проекта.
- Прошивки ESP32 собирать в окружении ESP-IDF (вне Docker, если иное не указано локальными инструкциями).
- Основные Docker-файлы:
  - `backend/docker-compose.dev.yml`
  - `backend/docker-compose.dev.win.yml`
  - `backend/docker-compose.ci.yml`
  - `backend/docker-compose.prod.yml`
  - `backend/laravel/Dockerfile`
  - `backend/services/*/Dockerfile`
  - `backend/services/Dockerfile.test`
  - `tests/e2e/docker-compose.e2e.yml`
  - `tests/node_sim/Dockerfile`
  - `infra/hil/docker-compose.hil.yml`

## 2) Контракты и совместимость

- Проект в разработке: несовместимые изменения допускаются только вне пайплайна и схем взаимодействия.
- Запрещены несовместимые изменения в пайплайне `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`
  и схемах взаимодействия (MQTT топики/полезная нагрузка, форматы команд, схемы БД, ключевые поля,
  обязательные ID, API-ответы, Inertia props).
- Если меняются API-ответы или Inertia props — обновить соответствующий фронтенд.
- При изменениях протоколов/данных в пайплайне явно указывать совместимость:
  `Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.
  Эту строку фиксировать в описании pull request (PR) или коммита и/или в обновляемой спецификации.

## 2.1) Чек-лист при изменениях протоколов/данных

- Обновить спецификации MQTT: `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`,
  `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`,
  `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`.
- При добавлении новых `message_type` или `channel` обновить
  `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` и обработчики Python.
- Обновить `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
- Если затронут путь публикации команд — обновить `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`.
- Если затронуты циклы коррекции pH/EC — обновить
  `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` и
  `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`.
- Если добавлена телеметрия — убедиться в записи `telemetry_samples` и `telemetry_last`.
- Если меняются API-ответы или Inertia props — обновить фронтенд.
- Указать строку `Compatible-With` (см. выше).

## 3) Правила по слоям

- Команды к узлам идут только через Python-слой с централизованной MQTT-публикацией в `history-logger`.
- Запрещено публиковать команды в MQTT напрямую из Laravel, scheduler и automation-engine.
- Базовый путь команд: `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.
- Laravel владеет схемой БД: любые изменения через миграции, без ручного DDL.
- При добавлении новых метрик телеметрии — обеспечить запись в `telemetry_samples`
  и `telemetry_last` (см. `doc_ai/05_DATA_AND_STORAGE`).

## 3.1) Laravel / БД / MQTT (уточнение)

- Laravel:
  - не обращаться к MQTT напрямую из Laravel, только через Python‑сервис
    (см. `doc_ai/10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md`).
  - роли/авторизацию (`auth/roles`) не менять без явной необходимости.
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

## 4.1) Лучшие практики постановки задач (GPT-5.x/Codex)

- Начинать с цели и причины изменения: что не так сейчас, почему это важно.
- Давать контекст слоя и связей: подсистема, ключевые файлы, внешние зависимости, версии.
- Указывать входные данные: примеры полезной нагрузки (payload), логи, схемы, конфиги, ссылки на документы.
- Явно прописывать ограничения: запреты, совместимость, требования к миграциям/схемам.
- Фиксировать критерии приёмки: ожидаемое поведение, пограничные случаи, метрики.
- Уточнять формат ответа: список файлов, шаги, таблицы, команды, риски/допущения.
- Добавлять предпочтения пользователя: стиль общения, глубина объяснений, темп итераций.
- Просить план и список затронутых файлов перед реализацией для сложных задач.
- Если данных недостаточно — требовать список вопросов, а не домыслы.

## 4.2) Мини-шаблон запроса (для глубокого контекста)

```
Роль: <кто нужен: разработчик/аналитик/ревьюер>.
Цель: <что нужно получить и зачем>.
Контекст: <подсистема, файлы, версии, связи>.
Входные артефакты: <логи, примеры, схемы, конфиги>.
Ограничения: <что нельзя менять, совместимость, безопасность>.
Критерии приёмки: <что считать успехом, пограничные случаи>.
Формат ответа: <итог/изменения/тесты, список файлов, команды>.
```

## 4.3) Упрощённый запрос (если нет времени на детали)

Достаточно 2-3 коротких фраз:

```
Нужно: <что сделать>.
Где: <подсистема/файлы, если известно>.
Важно: <ограничения или ожидания, если есть>.
```

## 5) Поведение ИИ

- Следовать `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` как базовому чек‑листу.
- Не придумывать архитектуру заново и не игнорировать спецификации.
- Если изменение затрагивает пайплайн/схемы взаимодействия и похоже на несовместимое или неочевидно,
  остановиться и запросить подтверждение.
- Всегда отвечать на русском языке; англоязычные термины использовать только как технические
  идентификаторы/имена API/протоколов.
