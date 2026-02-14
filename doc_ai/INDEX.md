# Индекс документации hydro 2.0

**Версия:** 2.0  
**Дата обновления:** 2025-12-26

Этот документ служит главной точкой входа в документацию проекта hydro 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 🗺️ Быстрая навигация

### Начало работы
- **[SYSTEM_ARCH_FULL.md](SYSTEM_ARCH_FULL.md)** — главный входной документ по архитектуре
- **[README_STRUCTURE.md](README_STRUCTURE.md)** — описание структуры документации
- **[DEV_CONVENTIONS.md](DEV_CONVENTIONS.md)** — конвенции разработки

### Работа с ИИ-агентами
- **[TASKS_FOR_AI_AGENTS.md](TASKS_FOR_AI_AGENTS.md)** — правила постановки задач для ИИ-агентов

---

## 📚 Структура документации по разделам

### [01_SYSTEM](01_SYSTEM/) — Системная архитектура
Высокоуровневая архитектура, логика, потоки данных.

**Ключевые документы:**
- `01_SYSTEM/LOGIC_ARCH.md` — логическая модель (Теплица → Зоны → Ноды → Каналы)
- `01_SYSTEM/DATAFLOW_FULL.md` — потоки данных (telemetry, commands, config)
- `01_SYSTEM/NODE_LIFECYCLE_AND_PROVISIONING.md` — жизненный цикл узлов
- `01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md` — структура проекта

**См. также:** [README](01_SYSTEM/README.md)

---

### [02_HARDWARE_FIRMWARE](02_HARDWARE_FIRMWARE/) — Железо и прошивки
Архитектура узлов ESP32, прошивки, каналы, конфигурация.

**Ключевые документы:**
- `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — полная архитектура узлов ESP32
- `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — справочник каналов узлов
- `02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` — спецификация NodeConfig
- `02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md` — структура прошивки
- `02_HARDWARE_FIRMWARE/HARDWARE_ARCH_FULL.md` — аппаратная архитектура

**См. также:** [README](02_HARDWARE_FIRMWARE/README.md)

---

### [03_TRANSPORT_MQTT](03_TRANSPORT_MQTT/) — MQTT транспорт
Протокол MQTT, топики, контракты, валидация.

**Ключевые документы:**
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — полная спецификация MQTT
- `03_TRANSPORT_MQTT/MQTT_NAMESPACE.md` — структура топиков
- `03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md` — контракт между backend и узлами
- `03_TRANSPORT_MQTT/COMMAND_VALIDATION_ENGINE.md` — валидация команд

**См. также:** [README](03_TRANSPORT_MQTT/README.md)

---

### [04_BACKEND_CORE](04_BACKEND_CORE/) — Backend (Laravel)
Архитектура backend, API, Python-сервисы, интеграции.

**Ключевые документы:**
- `04_BACKEND_CORE/BACKEND_ARCH_FULL.md` — архитектура backend
- `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python-сервисов
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md` — API-спецификация
- `04_BACKEND_CORE/REST_API_REFERENCE.md` — REST API справочник
- `04_BACKEND_CORE/TECH_STACK_LARAVEL_INERTIA_VUE3_PG.md` — технологический стек

**См. также:** [README](04_BACKEND_CORE/README.md)

---

### [05_DATA_AND_STORAGE](05_DATA_AND_STORAGE/) — Данные и хранилища
Модель данных, телеметрия, политики хранения.

**Ключевые документы:**
- `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — полный справочник моделей данных
- `05_DATA_AND_STORAGE/TELEMETRY_PIPELINE.md` — пайплайн телеметрии
- `05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md` — политики хранения данных

**См. также:** [README](05_DATA_AND_STORAGE/README.md)

---

### [06_DOMAIN_ZONES_RECIPES](06_DOMAIN_ZONES_RECIPES/) — Доменная логика
Контроллеры зон, рецепты, планировщики, события.

**Ключевые документы:**
- `06_DOMAIN_ZONES_RECIPES/ZONE_CONTROLLER_FULL.md` — контроллеры зон (pH, EC, климат, полив, свет)
- `06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md` — движок рецептов
- `06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — спецификация циклов коррекции раствора (pH/EC)
- `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets для контроллеров
- `06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md` — зоны и пресеты культур
- `06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md` — планировщик
- `06_DOMAIN_ZONES_RECIPES/EVENTS_AND_ALERTS_ENGINE.md` — события и алерты

**См. также:** [README](06_DOMAIN_ZONES_RECIPES/README.md)

---

### [07_FRONTEND](07_FRONTEND/) — Frontend и UI/UX
Архитектура фронтенда, UI/UX спецификация, тестирование.

**Ключевые документы:**
- `07_FRONTEND/FRONTEND_ARCH_FULL.md` — полная архитектура фронтенда
- `07_FRONTEND/FRONTEND_UI_UX_SPEC.md` — спецификация UI/UX
- `07_FRONTEND/FRONTEND_TESTING.md` — стратегия тестирования фронтенда

**См. также:** [README](07_FRONTEND/README.md)

---

### [08_SECURITY_AND_OPS](08_SECURITY_AND_OPS/) — Безопасность и эксплуатация
Безопасность, аутентификация, мониторинг, резервное копирование.

**Ключевые документы:**
- `08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md` — архитектура безопасности
- `08_SECURITY_AND_OPS/AUTH_SYSTEM.md` — система аутентификации
- `08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md` — резервное копирование и восстановление
- `08_SECURITY_AND_OPS/OPERATIONS_GUIDE.md` — руководство по эксплуатации
- `08_SECURITY_AND_OPS/RUNBOOKS.md` — процедуры восстановления

**См. также:** [README](08_SECURITY_AND_OPS/README.md)

---

### [09_AI_AND_DIGITAL_TWIN](09_AI_AND_DIGITAL_TWIN/) — AI и цифровой двойник
AI-архитектура, оптимизация, симуляция, цифровой двойник.

**Ключевые документы:**
- `09_AI_AND_DIGITAL_TWIN/AI_ARCH_FULL.md` — полная архитектура AI-слоя
- `09_AI_AND_DIGITAL_TWIN/DIGITAL_TWIN_ENGINE.md` — движок цифрового двойника
- `09_AI_AND_DIGITAL_TWIN/ZONE_SIMULATION_ENGINE.md` — симуляция зон
- `09_AI_AND_DIGITAL_TWIN/AI_OPTIMIZATION_ENGINE.md` — оптимизация

**См. также:** [README](09_AI_AND_DIGITAL_TWIN/README.md)

---

### [10_AI_DEV_GUIDES](10_AI_DEV_GUIDES/) — Гайды для ИИ-разработки
Руководства для работы с ИИ-агентами над различными компонентами.

**Ключевые документы:**
- `10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` — общий гайд для ИИ-ассистентов
- `10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md` — гайд по backend разработке
- `10_AI_DEV_GUIDES/DATABASE_SCHEMA_AI_GUIDE.md` — гайд по схеме БД
- `10_AI_DEV_GUIDES/MQTT_TOPICS_SPEC_AI_GUIDE.md` — гайд по MQTT
- `10_AI_DEV_GUIDES/ZONE_CONTROLLERS_AI_GUIDE.md` — гайд по контроллерам зон

**См. также:** [README](10_AI_DEV_GUIDES/README.md)

---

### [12_ANDROID_APP](12_ANDROID_APP/) — Android приложение
Архитектура, экраны, интеграция с API.

**Ключевые документы:**
- `12_ANDROID_APP/ANDROID_APP_ARCH.md` — архитектура Android-приложения
- `12_ANDROID_APP/ANDROID_APP_SCREENS.md` — описание экранов
- `12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md` — интеграция с API

**См. также:** [README](12_ANDROID_APP/README.md)

---

## 🔍 Поиск по темам

### Начало работы с проектом
1. Прочитайте `SYSTEM_ARCH_FULL.md`
2. Изучите `01_SYSTEM/LOGIC_ARCH.md` для понимания модели данных
3. Ознакомьтесь с `DEV_CONVENTIONS.md` для правил разработки

### Разработка прошивок ESP32
1. `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
2. `02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`
3. `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
4. `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

### Разработка backend
1. `04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
2. `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
3. `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
4. `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

### Разработка фронтенда
1. `07_FRONTEND/FRONTEND_ARCH_FULL.md`
2. `07_FRONTEND/FRONTEND_UI_UX_SPEC.md`
3. `07_FRONTEND/FRONTEND_TESTING.md`

### Работа с ИИ-агентами
1. `TASKS_FOR_AI_AGENTS.md`
2. `10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md`
3. Разделы `10_AI_DEV_GUIDES/` по конкретным компонентам

---

## 💡 Советы по использованию

1. **Начинайте с `SYSTEM_ARCH_FULL.md`** — это главный входной документ
2. **Используйте поиск** — большинство документов содержат перекрестные ссылки
3. **Читайте гайды для ИИ** — если работаете с ИИ-агентами, изучите `10_AI_DEV_GUIDES/`

---

## 📝 Примечания

- Документация в `doc_ai/` является **source of truth** и редактируется здесь
- `docs/` — mirror для совместимости, без ручных правок
- Все ссылки в документации должны быть относительными от корня `doc_ai/`

---

**Последнее обновление:** 2025-01-27
