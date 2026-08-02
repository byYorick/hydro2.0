# IMPLEMENTATION_STATUS.md
Статус реализации компонентов **hydro2.0**.

> ВАЖНО: этот файл — рабочий чек-лист. Его нужно регулярно обновлять вручную или полуавтоматически (скриптами/ИИ-агентами). 
> Статусы: `PLANNED`, `SPEC_READY`, `IN_PROGRESS`, `MVP_DONE`, `PROD_READY`.

Легенда:
- **PLANNED** — идея зафиксирована, но подробной спецификации нет.
- **SPEC_READY** — есть .md-спецификация, по которой можно писать код.
- **IN_PROGRESS** — ведётся активная разработка.
- **MVP_DONE** — реализован минимально жизнеспособный функционал, работает на тестовой установке.
- **PROD_READY** — отлажено на реальных объектах, покрыто тестами, задокументировано.

---

## 1. Архитектура и документация

- [x] `SYSTEM_ARCH_FULL.md` — **SPEC_READY**
- [x] `LOGIC_ARCH.md` — **SPEC_READY**
- [x] `DATAFLOW_FULL.md` — **SPEC_READY**
- [x] `NODE_LIFECYCLE_AND_PROVISIONING.md` — **SPEC_READY**
- [x] `REPO_MAPPING.md` — **SPEC_READY**
- [x] Миграция с mesh_hydro 1.x завершена в продукте; план — `archive` stub → `00_ARCHIVE/PLANS/MIGRATION_PLAN_FROM_MESH_HYDRO.md`
- [ ] `DEV_CONVENTIONS.md` — **SPEC_READY** (создан в рамках текущего шага)
- [ ] `ROADMAP_2.0.md` — **SPEC_READY** (создан в рамках текущего шага)
- [ ] Регулярный аудит документации и синхронизация с кодом — **PLANNED**

---

## 2. Ноды и прошивки ESP32

### 2.1. Общие компоненты

- [x] `NODE_ARCH_FULL.md` — **SPEC_READY**
- [x] `FIRMWARE_STRUCTURE.md` — **SPEC_READY**
- [x] `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — **SPEC_READY**
- [x] `NODE_OLED_UI_SPEC.md` — **SPEC_READY** (файл существует в `02_HARDWARE_FIRMWARE/`)
- [x] `SDKCONFIG_PROFILES.md` — **SPEC_READY**
- [x] Общий компонент `mqtt_client` (ESP-IDF) — **MVP_DONE**
- [x] Общий компонент `wifi_manager` — **MVP_DONE**
- [x] Общий компонент `config_storage` — **MVP_DONE** (спецификация в `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`)
- [x] Общий компонент `i2c_bus` (сенсоры) — **MVP_DONE**
- [x] Общий компонент `oled_ui` — **MVP_DONE**
- [x] Общий компонент `logging` — **MVP_DONE**

### 2.2. pH-node

- [x] `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — **SPEC_READY**
- [x] Инициализация ноды (Wi-Fi + MQTT + OLED) — **MVP_DONE** (реализовано в `ph_node_init.c`, `ph_node_app.c`)
- [x] Драйвер pH-датчика и чтение значения — **MVP_DONE** (компонент `trema_ph`)
- [x] Калибровка (2 этапа) — **MVP_DONE** (поддержка калибровки реализована)
- [x] Отправка телеметрии по MQTT — **MVP_DONE** (через `mqtt_manager`)
- [x] Экран состояния и ошибок — **MVP_DONE** (компонент `oled_ui`)
- [x] Обработка команд (`run_pump`, `dose`, `calibrate` / `calibrate_ph`) — **MVP_DONE** (отдельного `stop_pump` handler нет)
- [ ] MVP-тест на стенде — **IN_PROGRESS** (требуется тестирование на реальном оборудовании)

### 2.3. EC-node

- [x] `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — **SPEC_READY**
- [x] Драйвер EC-датчика — **MVP_DONE** (компонент `trema_ec`)
- [x] Компенсация по температуре — **MVP_DONE** (реализована в драйвере)
- [x] Отправка телеметрии по MQTT — **MVP_DONE** (через `mqtt_manager`)
- [x] Обработка команд (run_pump, calibrate) — **MVP_DONE**
- [x] OLED-интерфейс — **MVP_DONE** (`ec_node_init_step_oled` / `oled_ui_init`)
- [ ] MVP-тест — **IN_PROGRESS** (требуется тестирование на реальном оборудовании)

### 2.4. Climate-node

- [x] `02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md` — **SPEC_READY**
- [x] Поддержка основных сенсоров (температура, влажность через SHT3x) — **MVP_DONE** (компонент `sht3x`)
- [x] Поддержка CO₂ (CCS811) — **MVP_DONE** (канал `co2`; stub fallback при отсутствии HW)
- [x] Телеметрия по MQTT — **MVP_DONE** (структура реализована)
- [x] Обработка команд (set_relay, set_pwm) — **MVP_DONE**
- [ ] Аварии и пороги — **PLANNED**
- [ ] MVP-тест — **IN_PROGRESS** (требуется тестирование на реальном оборудовании)

### 2.5. Pump-node

- [x] Проект `firmware/nodes/pump_node` + MQTT/framework — **MVP_DONE**
- [x] Получение/исполнение команд по MQTT — **MVP_DONE**
- [x] INA209 / ток / overcurrent health — **MVP_DONE** (код интегрирован; HW-стенд отдельно)
- [ ] Dry-run guards — **PLANNED**
- [ ] MVP-тест на стенде — **IN_PROGRESS**

### 2.5.1. Storage irrigation node

- [x] Проект `firmware/nodes/storage_irrigation_node` (two-tank, level_switch, failsafe, `run_pump`) — **MVP_DONE**
- [x] Prod spec `STORAGE_IRRIGATION_NODE_PROD_SPEC.md` — **SPEC_READY**
- [ ] Полный HW acceptance на реальном стенде — **IN_PROGRESS**

### 2.6. Lighting-node (sensor)

- [x] Проект `firmware/nodes/light_node` — **сенсорная** нода (`trema_light`, metric `LIGHT`) — **MVP_DONE**
- [ ] Actuator PWM/WS2811 управление светом — **PLANNED** (не в текущей прошивке; `ws2811_driver` только guide)
- [ ] MVP-тест на стенде — **IN_PROGRESS**

### 2.7. Relay-node

- [x] Проект `firmware/nodes/relay_node` + MQTT/framework — **MVP_DONE**
- [ ] MVP-тест на стенде — **IN_PROGRESS**

### 2.8. test_node (HIL)

- [x] Проект `firmware/test_node` (multi-virtual nodes, контрактные сценарии) — **MVP_DONE** (HIL, не production)

---

## 3. Python-сервисы

- [x] Общая архитектура Python-сервисов описана (`PYTHON_SERVICES_ARCH.md`) — **SPEC_READY** (создан в `doc_ai/04_BACKEND_CORE/` и `backend/services/`)
- [x] Telemetry ingestor (`history-logger`: приём и запись данных из MQTT, батчинг, upsert в `telemetry_last`) — **MVP_DONE**
- [x] Zone controller (`automation-engine`: проверка targets, публикация команд корректировки pH/EC) — **MVP_DONE**
- [x] Scheduler ownership — **Laravel** `automation:dispatch-schedules` → intents → AE3 wake-up (`start-irrigation` / `start-lighting-tick` / `start-solution-topup` / `start-solution-change` / `start-cycle`); отдельный Python-контейнер `scheduler` **не** в compose и **не** публикует MQTT — **MVP_DONE**
- [x] Integration bridge (`mqtt-bridge`: FastAPI REST→MQTT / ops) — **MVP_DONE** (каноническая публикация **команд** к узлам — только `history-logger`)
- [x] Обработка `node_hello` в `history-logger` (регистрация узлов через MQTT) — **MVP_DONE**
- [x] Обработка `heartbeat` в `history-logger` (uptime, free_heap, rssi) — **MVP_DONE**
- [x] Публикация `NodeConfig`: Laravel `PublishNodeConfigJob` → history-logger → MQTT — **MVP_DONE**
- [x] Тесты (pytest) для automation-engine / history-logger / mqtt-bridge — **MVP_DONE**
- [x] Интеграционные AE3-тесты (`make test-ae` → `hydro_test`) — **MVP_DONE**

---

## 4. Backend (Laravel)

- [x] Архитектура backend (`04_BACKEND_CORE/BACKEND_ARCH_FULL.md` и связанные файлы) — **SPEC_READY**
- [x] Модели зон, нод, рецептов — **MVP_DONE**
- [x] REST API v1 (базовый набор эндпоинтов) — **MVP_DONE**
- [x] Авторизация/аутентификация (Breeze/Sanctum, web + api) — **MVP_DONE**
- [x] WebSocket/Realtime-обновления — **MVP_DONE**
- [x] Панель администрирования (минимальная) — **MVP_DONE**
- [x] Миграции БД и сиды — **MVP_DONE**
- [x] Интеграция с Python-сервисами (PythonIngestController для telemetry/commands, PythonBridgeService) — **MVP_DONE**
- [x] Жизненный цикл узлов (lifecycle_state, hardware_id, NodeLifecycleState Enum) — **MVP_DONE**
- [x] Регистрация узлов через MQTT (node_hello обработка) — **MVP_DONE**
- [x] NodeConfig генерация и публикация (NodeConfigService, автоматическая синхронизация) — **MVP_DONE**
- [x] Замена узлов (NodeSwapService, API endpoint) — **MVP_DONE**
- [x] Heartbeat метрики (uptime_seconds, free_heap_bytes, rssi в таблице nodes) — **MVP_DONE**

---

## 5. Хранилище данных и мониторинг

- [x] Модель данных и пайплайн телеметрии описаны (`05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` и т.п.) — **SPEC_READY**
- [x] Выбор конкретной СУБД/TSDB и настройка (PostgreSQL + TimescaleDB) — **MVP_DONE**
- [x] Настройка retention политик — **MVP_DONE**
- [x] Grafana/дашборды мониторинга — **MVP_DONE**
- [x] Алерты по ключевым метрикам (падение нод, брокера, сервисов) — **MVP_DONE**

---

## 6. Доменные зоны, рецепты, логика агрономии

- [x] Базовые концепции зон и рецептов описаны (`06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md` и т.п.) — **SPEC_READY**
- [x] Набор пресетов культур (салаты, зелень и т.д.) — **MVP_DONE** (6 пресетов: салат, руккола, томат/огурец, микрозелень, базилик, клубника)
- [x] Реализация в backend/Python (CRUD рецептов, применение к зонам) — **MVP_DONE** (RecipeController, RecipePhaseController, ZoneService::attachRecipe, интеграция с Python)
- [x] Отчётность по урожайности и эффективности рецептов — **MVP_DONE** (Harvest модель, RecipeAnalytics, ReportController с аналитикой и сравнением рецептов)

---

## 7. Frontend / Web UI

### 7.1. Документация и архитектура

- [x] Архитектура фронтенда (`07_FRONTEND/FRONTEND_ARCH_FULL.md`) — **SPEC_READY**
- [x] Спецификация UI/UX (`07_FRONTEND/FRONTEND_UI_UX_SPEC.md`) — **SPEC_READY**
- [x] Стратегия тестирования фронтенда (`07_FRONTEND/FRONTEND_TESTING.md`) — **SPEC_READY**

### 7.2. Основные страницы и экраны

- [x] Dashboard (обзор системы: статистика теплиц/зон/устройств, проблемные зоны, последние алерты) — **MVP_DONE**
- [x] Zones/Index (список всех зон с фильтрацией по статусу и поиском) — **MVP_DONE**
- [x] Zones/Show (детальный экран зоны — главный рабочий экран) — **MVP_DONE**
  - [x] Компонент ZoneTargets (Target vs Actual: pH, EC, температура, влажность с индикаторами статуса) — **MVP_DONE**
  - [x] Компонент ZoneTelemetryChart (графики pH/EC с выбором временного диапазона: 1H/24H/7D/30D/ALL) — **MVP_DONE**
  - [x] Блок Cycles (расписание подсистем: PH_CONTROL, EC_CONTROL, IRRIGATION, LIGHTING, CLIMATE с кнопками запуска) — **MVP_DONE**
  - [x] Интеграция с API для загрузки истории телеметрии через `/api/zones/{id}/telemetry/history` — **MVP_DONE**
  - [x] Отображение устройств зоны (Devices) — **MVP_DONE**
  - [x] Блок Events (история событий зоны с цветовой кодировкой) — **MVP_DONE**
  - [x] Кнопки управления (Pause/Resume, Irrigate Now, Next Phase) с отправкой команд через API — **MVP_DONE**
- [x] Devices/Index (список всех устройств с фильтрацией по типу и статусу) — **MVP_DONE**
- [x] Devices/Show (детальный экран устройства: каналы, NodeConfig, команды) — **MVP_DONE**
- [x] Recipes/Index (список рецептов с поиском) — **MVP_DONE**
- [x] Recipes/Show (детальный экран рецепта: фазы, цели) — **MVP_DONE**
- [x] Recipes/Edit (редактирование рецепта) — **MVP_DONE**
- [x] Alerts/Index (экран аварий/уведомлений с фильтрацией и управлением) — **MVP_DONE**
- [x] Settings/Index (настройки: профиль пользователя, управление пользователями для admin) — **MVP_DONE**
- [x] Admin панель (Index, Zones, Recipes) — **MVP_DONE**
- [x] Аутентификация (Login, Register, Password Reset) — **MVP_DONE**

### 7.3. Компоненты и UI элементы

- [x] AppLayout (главный layout с навигацией, Command Palette, контекстная панель) — **MVP_DONE**
- [x] ZoneTargets (компонент Target vs Actual с индикаторами статуса) — **MVP_DONE**
- [x] ZoneTelemetryChart (компонент графиков телеметрии с ECharts) — **MVP_DONE**
- [x] ZoneCard (карточка зоны для списка) — **MVP_DONE**
- [x] CommandPalette (командная палитра Ctrl+K) — **MVP_DONE**
- [x] Badge (компонент статусных бейджей: success/warning/danger/info/neutral) — **MVP_DONE**
- [x] ChartBase (базовый компонент графиков на ECharts) — **MVP_DONE**
- [x] DeviceChannelsTable (таблица каналов устройства) — **MVP_DONE**
- [x] Базовые UI компоненты (Card, Button, Modal, Input, Dropdown, DataTable и др.) — **MVP_DONE**

### 7.4. Real-time и WebSocket

- [x] Laravel Echo интеграция в `bootstrap.js` (поддержка WebSocket через Pusher/Reverb) — **MVP_DONE**
- [x] WebSocket подписка на алерты (`subscribeAlerts` в `bootstrap.js`) — **MVP_DONE**
  - [x] Использование в Alerts/Index для real-time обновлений — **MVP_DONE**
- [x] WebSocket подписка на зоны (`subscribeZone` в `bootstrap.js`, возвращает функцию отписки) — **MVP_DONE**
  - [x] Использование в Zones/Show для real-time обновления команд — **MVP_DONE** (через `subscribeToZoneCommands`)
  - [x] Real-time обновление телеметрии через store events — **MVP_DONE** (через `useStoreEvents` и `useTelemetryBatch`)
- [x] Real-time обновление графиков телеметрии без перезагрузки страницы — **MVP_DONE** (обновление через batch updates)

### 7.5. State Management

- [x] Pinia stores (zones, devices, alerts) — **MVP_DONE**
- [x] Интеграция с Inertia.js для серверного state — **MVP_DONE**

### 7.6. Тестирование

- [x] Unit-тесты компонентов (ZoneTargets, ZoneTelemetryChart, Badge) — **MVP_DONE**
  - [x] Тесты граничных случаев (ZoneTargets edge cases) — **MVP_DONE**
- [x] Интеграционные тесты страниц (Zones/Show, Zones/Index, Alerts/Index, Devices/Index) — **MVP_DONE**
- [x] E2E тесты (Playwright: smoke, zones-show, filters) — **MVP_DONE**
- [x] Конфигурация тестов (Vitest, Playwright) — **MVP_DONE**
- [ ] Тесты для Recipes страниц — **PLANNED**
- [ ] Тесты для Devices/Show — **PLANNED**
- [ ] Тесты для WebSocket-обновлений — **PLANNED**

### 7.7. Дополнительные функции

- [x] Фильтрация и поиск (Zones, Devices, Alerts, Recipes) — **MVP_DONE**
- [x] Виртуализация списков для производительности — **MVP_DONE**
- [x] Обработка ошибок API с логированием — **MVP_DONE**
- [ ] Переключатель темы (Dark/Light) — **PLANNED** (текущая реализация: только dark тема)
- [x] AI Prediction card в automation tab — **MVP_DONE** (линейный прогноз; полный AI Panel/чат — **PLANNED**)
- [ ] Горячие клавиши для навигации (Shift+Z, Shift+D и т.д.) — **PLANNED**
- [ ] Избранные зоны (pin zones) — **PLANNED**

---

## 8. Android-приложение

Код: `mobile/app/android/` (см. `doc_ai/12_ANDROID_APP/`).

- [x] Архитектура приложения (`ANDROID_APP_ARCH.md`, `ANDROID_APP_SCREENS.md`, `ANDROID_APP_API_INTEGRATION.md`) — **SPEC_READY** / частично реализовано
- [x] Авторизация и выбор теплицы/зоны — **IN_PROGRESS** (`LoginScreen`, `GreenhousesScreen`, `ZonesScreen`)
- [x] Просмотр текущих параметров зон — **IN_PROGRESS** (`ZoneDetailsScreen` + телеметрия)
- [x] Просмотр аварий и ack — **IN_PROGRESS** (`AlertsScreen`)
- [x] Минимальное управление (команды с zone details) — **IN_PROGRESS** (`sendCommand`)
- [x] Provisioning scaffold — **IN_PROGRESS** (`ProvisioningScreen`)
- [ ] Полный Clean Architecture / node-details / MQTT-клиент — **PLANNED** (сейчас REST + WebSocket/polling)
- [ ] Публикация тестовой сборки (internal testing) — **PLANNED**

---

## 9. Безопасность, DevOps и эксплуатация

- [x] Основные требования безопасности и DevOps описаны (`SECURITY_AND_OPS.md` и связанные) — **SPEC_READY**
- [x] CI/CD-конвейер (проверки, сборка, деплой) — **MVP_DONE**
  - GitHub Actions: Postgres сервис, `migrate:fresh --seed` перед тестами
  - Vitest: JUnit-отчёт и coverage (артефакты Actions)
  - Playwright: HTML‑репорт (артефакт Actions)
  - Кэш Composer/NPM, конфиг‑кеши Laravel
- [x] Резервное копирование и восстановление (manual + scripted) — **MVP_DONE**
  - Скрипты автоматического бэкапа: PostgreSQL, Laravel, Python, MQTT, Docker volumes
  - Master скрипт `full_backup.sh` для координации всех бэкапов
  - WAL архивирование PostgreSQL настроено
  - Скрипты восстановления: PostgreSQL, Laravel, полное восстановление
  - Ротация бэкапов (30 дней полных, 7 дней WAL)
  - Laravel Artisan команды: `backup:database`, `backup:full`, `backup:list`
  - Автоматическое расписание бэкапов (ежедневно в 3:00)
- [x] Документация по эксплуатации и ручным процедурам — **MVP_DONE**
  - `OPERATIONS_GUIDE.md` с ежедневными, еженедельными и ежемесячными операциями
  - Процедуры обновления системы
  - Процедуры масштабирования
- [x] Набор runbook'ов на случай аварий — **MVP_DONE**
  - Расширенный `RUNBOOKS.md` с процедурами восстановления
  - Процедуры диагностики бэкапов
  - Процедуры для аварийных ситуаций (полный сбой, потеря БД, потеря MQTT, потеря узлов ESP32)

---

## 10. AI и Digital Twin

- [x] Общая концепция AI/digital twin (`09_AI_AND_DIGITAL_TWIN/AI_ARCH_FULL.md` или аналог) — **SPEC_READY**
- [x] Базовые гайды для ИИ-разработки (`10_AI_DEV_GUIDES`) — **SPEC_READY**
- [x] Сервис `backend/services/digital-twin` (solvers, calibrators, live sim, `zone_dt_params`) — **MVP_DONE** (код есть; не путать с «полная agro-autonomy»)
- [x] Первая модель прогноза параметров в UI — **MVP_DONE** (`PredictionService` linear regression + `AIPredictionCard` / ZoneAutomationTab; не ML pipeline из `ML_FEATURE_PIPELINE`)
- [ ] Полный AI Panel (чат, advanced recommend) — **PLANNED**

---

## 11. Логика этапов (roadmap)

Связка с `ROADMAP_2.0.md`:

- Для **Этапа 1 (MVP)** критичны:
 - pH/EC/climate/irrigation ноды;
 - MQTT + базовые Python-сервисы;
 - базовый backend + веб UI;
 - минимальное Android-приложение.
- Для **Этапа 2** добавляются:
 - сложные рецепты, AI-подсказки, улучшенный UI;
 - расширенный мониторинг и уведомления.
- Для **Этапа 3+** — мультисайтовость, масштабирование, интеграции.

При планировании спринтов и задач для ИИ-агентов рекомендуется ссылаться на этот файл и **явно ставить цель по статусу**: 
например, “поднять pH-node с `SPEC_READY` до `MVP_DONE` для одной тестовой установки”.
