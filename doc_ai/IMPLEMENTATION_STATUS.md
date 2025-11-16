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
- [ ] Общий компонент `mqtt_client` (ESP-IDF) — **PLANNED**
- [ ] Общий компонент `i2c_bus` (сенсоры) — **PLANNED**
- [ ] Общий компонент `oled_ui` — **PLANNED**
- [ ] Общий компонент `config_storage` — **PLANNED**
- [ ] Общий компонент `logging` — **PLANNED**

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

- [x] Общая архитектура Python-сервисов описана (`PYTHON_SERVICES_ARCH.md` или аналог) — **SPEC_READY**
- [ ] Telemetry ingestor (приём и запись данных из MQTT) — **PLANNED**
- [ ] Zone controller (управление поливом/дозированием по правилам) — **PLANNED**
- [ ] Scheduler (расписания поливов, света) — **PLANNED**
- [ ] Integration bridge (связка с backend при необходимости) — **PLANNED**
- [ ] Тесты и локальный docker-compose стенд — **PLANNED**

---

## 4. Backend (Laravel)

- [x] Архитектура backend (`04_BACKEND_CORE/BACKEND_ARCH_FULL.md` и связанные файлы) — **SPEC_READY**
- [ ] Модели зон, нод, рецептов — **PLANNED**
- [ ] REST API v1 (базовый набор эндпоинтов) — **PLANNED**
- [ ] Авторизация/аутентификация — **PLANNED**
- [ ] WebSocket/Realtime-обновления — **PLANNED**
- [ ] Панель администрирования (минимальная) — **PLANNED**
- [ ] Миграции БД и сиды — **PLANNED**
- [ ] Интеграция с Python-сервисами — **PLANNED**

---

## 5. Хранилище данных и мониторинг

- [x] Модель данных и пайплайн телеметрии описаны (`05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` и т.п.) — **SPEC_READY**
- [ ] Выбор конкретной СУБД/TSDB и настройка (PostgreSQL, InfluxDB и т.д.) — **PLANNED**
- [ ] Настройка retention политик — **PLANNED**
- [ ] Grafana/дашборды мониторинга — **PLANNED**
- [ ] Алерты по ключевым метрикам (падение нод, брокера, сервисов) — **PLANNED**

---

## 6. Доменные зоны, рецепты, логика агрономии

- [x] Базовые концепции зон и рецептов описаны (`06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md` и т.п.) — **SPEC_READY**
- [ ] Набор пресетов культур (салаты, зелень и т.д.) — **PLANNED**
- [ ] Реализация в backend/Python (CRUD рецептов, применение к зонам) — **PLANNED**
- [ ] Отчётность по урожайности и эффективности рецептов — **PLANNED**

---

## 7. Frontend / Web UI

- [x] Архитектура фронтенда и макеты (`07_FRONTEND/FRONTEND_ARCH_FULL.md`, `07_FRONTEND/FRONTEND_UI_UX_SPEC.md`) — **SPEC_READY**
- [ ] Экран обзора системы (все зоны/теплицы) — **PLANNED**
- [ ] Экран детали зоны (телеметрия, рецепты, полив) — **PLANNED**
- [ ] Графики истории параметров — **PLANNED**
- [ ] Экран аварий/уведомлений — **PLANNED**
- [ ] Экран настроек пользователей и прав — **PLANNED**

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
- [ ] CI/CD-конвейер (проверки, сборка, деплой) — **PLANNED**
- [ ] Резервное копирование и восстановление (manual + scripted) — **PLANNED**
- [ ] Документация по эксплуатации и ручным процедурам — **PLANNED**
- [ ] Набор runbook'ов на случай аварий — **PLANNED**

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
