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
- [x] `MIGRATION_PLAN_FROM_MESH_HYDRO.md` — **SPEC_READY**
- [ ] `DEV_CONVENTIONS.md` — **SPEC_READY** (создан в рамках текущего шага)
- [ ] `ROADMAP_2.0.md` — **SPEC_READY** (создан в рамках текущего шага)
- [ ] Регулярный аудит документации и синхронизация с кодом — **PLANNED**

---

## 2. Ноды и прошивки ESP32

### 2.1. Общие компоненты

- [x] `NODE_ARCH_FULL.md` — **SPEC_READY**
- [x] `FIRMWARE_STRUCTURE.md` — **SPEC_READY**
- [x] `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — **SPEC_READY**
- [x] `I2C_BUS_AND_SENSORS.md` — **SPEC_READY**
- [x] `OLED_UI_SPEC.md` — **SPEC_READY**
- [x] `SDKCONFIG_PROFILES.md` — **SPEC_READY**
- [x] Общий компонент `mqtt_client` (ESP-IDF) — **MVP_DONE**
- [x] Общий компонент `wifi_manager` — **MVP_DONE**
- [x] Общий компонент `config_storage` — **MVP_DONE** (спецификация в `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`)
- [x] Общий компонент `i2c_bus` (сенсоры) — **MVP_DONE**
- [x] Общий компонент `oled_ui` — **MVP_DONE**
- [x] Общий компонент `logging` — **MVP_DONE**

### 2.2. pH-node

- [x] `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — **SPEC_READY**
- [ ] Инициализация ноды (Wi-Fi + MQTT + OLED) — **PLANNED**
- [ ] Драйвер pH-датчика и чтение значения — **PLANNED**
- [ ] Калибровка (2–3 точки) — **PLANNED**
- [ ] Отправка телеметрии по MQTT — **PLANNED**
- [ ] Экран состояния и ошибок — **PLANNED**
- [ ] MVP-тест на стенде — **PLANNED**

### 2.3. EC-node

- [x] `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — **SPEC_READY**
- [ ] Драйвер EC-датчика — **PLANNED**
- [ ] Компенсация по температуре — **PLANNED**
- [ ] Отправка телеметрии по MQTT — **PLANNED**
- [ ] OLED-интерфейс — **PLANNED**
- [ ] MVP-тест — **PLANNED**

### 2.4. Climate-node

- [x] `02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md` — **SPEC_READY**
- [ ] Поддержка основных сенсоров (температура, влажность, CO₂ при наличии) — **PLANNED**
- [ ] Телеметрия по MQTT — **PLANNED**
- [ ] Аварии и пороги — **PLANNED**
- [ ] MVP-тест — **PLANNED**

### 2.5. Irrigation-node

- [x] `02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md` — **SPEC_READY**
- [ ] Управление помпами/клапанами — **PLANNED**
- [ ] Счётчик поливов / литраж (если есть расходомер) — **PLANNED**
- [ ] Обработка аварий (сухой ход, ошибки) — **PLANNED**
- [ ] Получение команд по MQTT — **PLANNED**
- [ ] MVP-тест — **PLANNED**

### 2.6. Lighting-node

- [x] `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — **SPEC_READY**
- [ ] Управление мощностью/каналами света — **PLANNED**
- [ ] Работа по расписанию/рецептам — **PLANNED**
- [ ] MVP-тест — **PLANNED**

---

## 3. Python-сервисы

- [x] Общая архитектура Python-сервисов описана (`PYTHON_SERVICES_ARCH.md`) — **SPEC_READY** (создан в `doc_ai/04_BACKEND_CORE/` и `backend/services/`)
- [x] Telemetry ingestor (`history-logger`: приём и запись данных из MQTT, батчинг, upsert в `telemetry_last`) — **MVP_DONE**
- [x] Zone controller (`automation-engine`: проверка targets, публикация команд корректировки pH/EC) — **MVP_DONE**
- [x] Scheduler (`scheduler`: расписания поливов/света из recipe phases, публикация команд на MQTT) — **MVP_DONE**
- [x] Integration bridge (`mqtt-bridge`: FastAPI для отправки команд через MQTT) — **MVP_DONE**
- [x] Тесты (pytest) для automation-engine и scheduler — **MVP_DONE**
- [ ] Интеграционные тесты в docker-compose стенде — **PLANNED**

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
  - [ ] Использование в Zones/Show для real-time обновления телеметрии — **PLANNED**
- [ ] Real-time обновление графиков телеметрии без перезагрузки страницы — **PLANNED**

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
- [ ] AI Panel (рекомендации, прогнозы, чат) — **PLANNED**
- [ ] Горячие клавиши для навигации (Shift+Z, Shift+D и т.д.) — **PLANNED**
- [ ] Избранные зоны (pin zones) — **PLANNED**

---

## 8. Android-приложение

- [x] Архитектура приложения (`ANDROID_APP_ARCH.md`, `ANDROID_APP_SCREENS.md`) — **SPEC_READY**
- [ ] Авторизация и выбор фермы/теплицы/зоны — **PLANNED**
- [ ] Просмотр текущих параметров зон — **PLANNED**
- [ ] Просмотр аварий и уведомлений — **PLANNED**
- [ ] Минимальное управление (вкл/выкл полив, свет, пауза рецепта) — **PLANNED**
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
- [ ] Первая модель прогноза параметров (например, pH/EC) — **PLANNED**
- [ ] Базовый digital twin для одной зоны — **PLANNED**
- [ ] Интеграция AI-подсказок в UI — **PLANNED**

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
