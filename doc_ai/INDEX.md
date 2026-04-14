# Индекс документации hydro 2.0

**Версия:** 2.1  
**Дата обновления:** 2026-04-10

Этот документ служит главной точкой входа в документацию проекта hydro 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 🗺️ Быстрая навигация

### Начало работы
- **[SYSTEM_ARCH_FULL.md](SYSTEM_ARCH_FULL.md)** — главный входной документ по архитектуре
- **[ARCHITECTURE_FLOWS.md](ARCHITECTURE_FLOWS.md)** — защищённые pipeline и инварианты AE3
- **[README_STRUCTURE.md](README_STRUCTURE.md)** — описание структуры документации
- **[DEV_CONVENTIONS.md](DEV_CONVENTIONS.md)** — конвенции разработки
- **[11_WEBSOCKET_ARCHITECTURE.md](11_WEBSOCKET_ARCHITECTURE.md)** — WebSocket (Reverb) и real-time UI

### Работа с ИИ-агентами
- **[TASKS_FOR_AI_AGENTS.md](TASKS_FOR_AI_AGENTS.md)** — правила постановки задач для ИИ-агентов

---

## 📚 Структура документации по разделам

### [01_SYSTEM](01_SYSTEM/) — Системная архитектура
Высокоуровневая архитектура, логика, потоки данных.

**Ключевые документы:**
- `01_SYSTEM/LOGIC_ARCH.md` — логическая модель (Теплица → Зоны → Ноды → Каналы)
- `01_SYSTEM/DATAFLOW_FULL.md` — потоки данных (telemetry, commands, config)
- `01_SYSTEM/PUMP_NAMING_UNIFICATION_PLAN.md` — системный план перехода к единым canonical именам насосов
- `01_SYSTEM/NODE_LIFECYCLE_AND_PROVISIONING.md` — жизненный цикл узлов
- `01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md` — структура проекта

**См. также:** [README](01_SYSTEM/README.md)

---

### [02_HARDWARE_FIRMWARE](02_HARDWARE_FIRMWARE/) — Железо и прошивки
Архитектура узлов ESP32, прошивки, каналы, конфигурация.

**Ключевые документы:**
- `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — полная архитектура узлов ESP32
- `02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md` — логика работы узлов
- `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — справочник каналов узлов
- `02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` — спецификация NodeConfig
- `02_HARDWARE_FIRMWARE/CONFIG_REPORT_HANDLING.md` — обработка config_report
- `02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md` — структура прошивки
- `02_HARDWARE_FIRMWARE/HARDWARE_ARCH_FULL.md` — аппаратная архитектура
- `02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md` — стандарты кодирования C/ESP-IDF
- `02_HARDWARE_FIRMWARE/SDKCONFIG_PROFILES.md` — профили sdkconfig
- `02_HARDWARE_FIRMWARE/OTA_UPDATE_PROTOCOL.md` — протокол OTA-обновлений
- `02_HARDWARE_FIRMWARE/WIFI_CONNECTIVITY_ENGINE.md`, `WIFI_PROVISIONING_FIRST_RUN.md` — Wi-Fi
- `02_HARDWARE_FIRMWARE/NODE_DIAGNOSTICS_ENGINE.md`, `NODE_INPUT_CONTROLS.md`, `NODE_OLED_UI_SPEC.md` — диагностика, UI узлов
- `02_HARDWARE_FIRMWARE/STORAGE_IRRIGATION_NODE_PROD_SPEC.md` — irrigation-node prod spec
- `02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`, `TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md` — test-node
- `02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md` — device-node протокол

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
- `04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md` — единый authority automation/runtime-конфигов
- `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python-сервисов
- `04_BACKEND_CORE/ae3lite.md` — каноническая спецификация AE3-Lite (automation-engine), rollout/rollback
- `04_BACKEND_CORE/AE3_RUNTIME_EVENT_CONTRACT.md` — runtime-event контракт AE3
- `04_BACKEND_CORE/AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` — failsafe / E-Stop контракт irrigation
- `04_BACKEND_CORE/AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md` — channel-level events для level_switch
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md` — API-спецификация
- `04_BACKEND_CORE/REST_API_REFERENCE.md` — REST API справочник
- `04_BACKEND_CORE/HISTORY_LOGGER_API.md` — контракт публикации команд и ingest
- `04_BACKEND_CORE/ERROR_CODE_CATALOG.md` — каталог кодов ошибок backend/AE3
- `04_BACKEND_CORE/END_TO_END_WORKFLOW_GUIDE.md` — сквозные сценарии и точки интеграции
- `04_BACKEND_CORE/REALTIME_UPDATES_ARCH.md` — архитектура real-time обновлений
- `04_BACKEND_CORE/FULL_STACK_DEPLOY_DOCKER.md` — деплой стека через Docker
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
- `06_DOMAIN_ZONES_RECIPES/ZONE_LOGIC_FLOW.md` — сквозная логика зоны (телеметрия → контроллеры → команды → UI)
- `06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md` — движок рецептов
- `06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — спецификация циклов коррекции раствора (pH/EC)
- `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets для контроллеров
- `06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md` — зоны и пресеты культур
- `06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md` — планировщик
- `06_DOMAIN_ZONES_RECIPES/SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` — dispatch не-полива для AE3 (lighting реализован, diagnostics через compat-path)
- `06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md` — справочник PID-конфигов
- `06_DOMAIN_ZONES_RECIPES/WATER_FLOW_ENGINE.md` — движок водного потока
- `06_DOMAIN_ZONES_RECIPES/EVENTS_AND_ALERTS_ENGINE.md` — события и алерты
- `06_DOMAIN_ZONES_RECIPES/ALERTS_AND_NOTIFICATIONS_CHANNELS.md` — каналы алертов/уведомлений

**См. также:** [README](06_DOMAIN_ZONES_RECIPES/README.md)

---

### [07_FRONTEND](07_FRONTEND/) — Frontend и UI/UX
Архитектура фронтенда, UI/UX спецификация, тестирование.

**Ключевые документы:**
- `07_FRONTEND/FRONTEND_ARCH_FULL.md` — полная архитектура фронтенда
- `07_FRONTEND/FRONTEND_UI_UX_SPEC.md` — спецификация UI/UX
- `07_FRONTEND/ROLE_BASED_UI_SPEC.md` — UI по ролям (`useRole`, dashboard'ы)
- `07_FRONTEND/API_MAPPING.md` — маппинг frontend → backend API
- `07_FRONTEND/FRONTEND_TESTING.md` — стратегия тестирования фронтенда
- `07_FRONTEND/ui_refs/` — референсы UI/UX (изображения)

**См. также:** [README](07_FRONTEND/README.md)

---

### [08_SECURITY_AND_OPS](08_SECURITY_AND_OPS/) — Безопасность и эксплуатация
Безопасность, аутентификация, мониторинг, резервное копирование.

**Ключевые документы:**
- `08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md` — архитектура безопасности
- `08_SECURITY_AND_OPS/FULL_SYSTEM_SECURITY.md` — полный обзор безопасности
- `08_SECURITY_AND_OPS/AUTH_SYSTEM.md` — система аутентификации
- `08_SECURITY_AND_OPS/LOGGING_AND_MONITORING.md` — логи, метрики, алертинг
- `08_SECURITY_AND_OPS/MONITORING_USER_GUIDE.md` — Grafana и дашборды для оператора
- `08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md` — резервное копирование и восстановление
- `08_SECURITY_AND_OPS/SYSTEM_FAILURE_RECOVERY.md` — восстановление после сбоев
- `08_SECURITY_AND_OPS/OPERATIONS_GUIDE.md` — руководство по эксплуатации
- `08_SECURITY_AND_OPS/RUNBOOKS.md` — процедуры восстановления
- `08_SECURITY_AND_OPS/TESTING_AND_CICD_STRATEGY.md` — стратегия тестирования и CI/CD

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
- `10_AI_DEV_GUIDES/HYDRO_PROMPTING_GUIDE.md` — промпты под репозиторий
- `10_AI_DEV_GUIDES/GPT5_PROMPTING_GUIDE.md` — расширенный гайд по промптам GPT-5
- `10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md` — гайд по backend разработке
- `10_AI_DEV_GUIDES/DATABASE_SCHEMA_AI_GUIDE.md` — гайд по схеме БД
- `10_AI_DEV_GUIDES/MQTT_TOPICS_SPEC_AI_GUIDE.md` — гайд по MQTT
- `10_AI_DEV_GUIDES/PYTHON_MQTT_SERVICE_AI_GUIDE.md` — гайд по Python MQTT-сервисам
- `10_AI_DEV_GUIDES/AI_TASK_TEMPLATES_AND_PATTERNS.md` — шаблоны задач для ИИ
- `10_AI_DEV_GUIDES/DEV_TASKS_FOR_AI_ASSISTANTS_SPEC.md` — спецификация постановки задач
- `10_AI_DEV_GUIDES/OPERATOR_TASKS_FOR_AI_SPEC.md` — задачи оператора для ИИ
- `10_AI_DEV_GUIDES/TASK_UNIFIED_DASHBOARD.md` — единый дашборд задач
- домен контроллеров зон: `06_DOMAIN_ZONES_RECIPES/ZONE_CONTROLLER_FULL.md`, `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`

**См. также:** [README](10_AI_DEV_GUIDES/README.md)

---

### [12_ANDROID_APP](12_ANDROID_APP/) — Android приложение
Архитектура, экраны, интеграция с API.

**Ключевые документы:**
- `12_ANDROID_APP/ANDROID_APP_ARCH.md` — архитектура Android-приложения
- `12_ANDROID_APP/ANDROID_APP_SCREENS.md` — описание экранов
- `12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md` — интеграция с API
- `12_ANDROID_APP/ANDROID_GROW_CYCLE_UI.md` — UI цикла выращивания

**См. также:** [README](12_ANDROID_APP/README.md)

---

### [13_TESTING](13_TESTING/) — Тестирование и E2E

E2E-сценарии, симулятор узлов, troubleshooting.

**Ключевые документы:**
- `13_TESTING/TESTING_OVERVIEW.md` — обзор стратегии тестирования
- `13_TESTING/E2E_GUIDE.md` — подробное руководство по E2E
- `13_TESTING/E2E_SCENARIOS.md` — полный список сценариев и DoD
- `13_TESTING/E2E_SETUP.md` — настройка E2E окружения
- `13_TESTING/AUTH_IN_E2E.md` — авторизация в E2E
- `13_TESTING/NODE_SIM.md` — симулятор узлов
- `13_TESTING/TROUBLESHOOTING.md` — troubleshooting тестов

**См. также:** [README](13_TESTING/README.md)

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
2. `04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md`
3. `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
4. `05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

### Разработка фронтенда
1. `07_FRONTEND/FRONTEND_ARCH_FULL.md`
2. `07_FRONTEND/FRONTEND_UI_UX_SPEC.md`
3. `07_FRONTEND/FRONTEND_TESTING.md`

### Тестирование и E2E
1. `13_TESTING/TESTING_OVERVIEW.md`
2. `13_TESTING/E2E_GUIDE.md`
3. `13_TESTING/E2E_SCENARIOS.md` + `13_TESTING/NODE_SIM.md`
4. `13_TESTING/TROUBLESHOOTING.md`

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

- Документация в `doc_ai/` является **единственным source of truth** и редактируется только здесь
- Все ссылки в документации должны быть относительными от корня `doc_ai/`
- Папка `docs/` удалена; уникальные материалы по тестированию перенесены в `13_TESTING/`, mobile UI — в `12_ANDROID_APP/`, UI-референсы — в `07_FRONTEND/ui_refs/`

---

**Последнее обновление:** 2026-04-10
