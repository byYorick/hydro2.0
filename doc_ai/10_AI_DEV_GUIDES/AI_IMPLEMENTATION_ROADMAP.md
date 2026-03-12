# AI_IMPLEMENTATION_ROADMAP.md
# Дорожная карта реализации Hydro 2.0 силами ИИ-агентов
# Очередность работ • Конкретные задачи • Ссылки на спеки

Этот документ предназначен для:
- meta-агента (который раздаёт задачи другим ИИ),
- людей, которые хотят быстро понимать, **что ещё не сделано** и в каком порядке.

Он привязывает архитектурные .md-файлы к **реальным задачам разработки**.

---

## 0. Условные обозначения

- **P0** — критично для первого рабочего релиза (MVP).
- **P1** — важно для удобства и стабильности, можно делать после P0.
- **P2** — улучшения, оптимизации, nice-to-have.

Для каждой задачи указываются:
- «Тип задачи» — какие AI-шаблоны использовать (см. `AI_TASK_TEMPLATES_AND_PATTERNS.md`);
- «Связанные документы» — что обязательно читать перед работой.

---

## 1. Firmware: общая платформа узлов

### 1.1. Общий каркас проекта ESP-IDF для узла (P0)

**Цель:** создать эталонный ESP-IDF-проект узла 2.0 (template), который потом клонируется под pH/EC/климат/свет.

- Тип задачи: «изменение/добавление прошивки узла».
- Что сделать:
 1. Создать структуру проекта:
 - `main/main.c`
 - `components/hw_i2c/`, `components/wifi_engine/`, `components/mqtt_engine/`,
 `components/node_config/`, `components/ui_oled/`, `components/input_controls/`, `components/diag/`.
 2. Реализовать заглушки задач:
 - `wifi_task`, `mqtt_task`, `sensor_task`, `ui_task`, `input_task`, `diag_task`.
 3. Настроить базовые `sdkconfig.debug` и `sdkconfig.release`.
- Связанные документы:
 - `SYSTEM_ARCH_FULL.md`
 - `HARDWARE_ARCH_FULL.md`
 - `ESP32_C_CODING_STANDARDS.md`
 - `SDKCONFIG_PROFILES.md`
 - `NODE_OLED_UI_SPEC.md`
 - `NODE_INPUT_CONTROLS.md`
 - `WIFI_PROVISIONING_FIRST_RUN.md`
 - `NODE_LIFECYCLE_AND_PROVISIONING.md`

---

### 1.2. Реализация Wi-Fi provisioning + lifecycle (P0)

**Цель:** в рамках эталонного проекта реализовать рабочий Wi-Fi provisioning и переход в нормальный режим.

- Тип задачи: «изменение/добавление прошивки узла».
- Что сделать:
 1. Реализовать state machine Wi-Fi согласно `WIFI_PROVISIONING_FIRST_RUN.md`.
 2. Поднять AP-режим и HTTP-конфигуратор (`/` и `/configure`).
 3. Интегрировать с NVS (чтение/запись `wifi_config`).
 4. Связать c UI:
 - экраны `WIFI_PROVISIONING`, `WIFI_CONNECTING`, `MQTT_CONNECTING`, `NORMAL`.
- Связанные документы:
 - `WIFI_PROVISIONING_FIRST_RUN.md`
 - `NODE_OLED_UI_SPEC.md`
 - `NODE_INPUT_CONTROLS.md`
 - `NODE_LIFECYCLE_AND_PROVISIONING.md`

---

### 1.3. Реализация UI на OLED + input-controls (P0)

**Цель:** сделать минимально рабочий UI, который отображает состояние узла и позволяет входить в калибровку/сброс Wi-Fi.

- Тип задачи: прошивка узла.
- Что сделать:
 1. Реализовать компонент `ui_oled` согласно `NODE_OLED_UI_SPEC.md`.
 2. Реализовать компонент `input_controls` и маппинг физических кнопок/энкодера.
 3. Связать их через очередь событий `ui_event_queue`.
- Связанные документы:
 - `NODE_OLED_UI_SPEC.md`
 - `NODE_INPUT_CONTROLS.md`
 - `ESP32_C_CODING_STANDARDS.md`

---

## 2. Firmware: специализированные ноды

### 2.1. PH-нода (P0)

**Цель:** законченная pH-нода 2.0 (измерение pH, температура, калибровка, отправка в MQTT).

- Тип задачи: прошивка узла.
- Что сделать:
 1. Добавить компонент `sensors_ph`.
 2. Реализовать:
 - чтение датчика pH (по I²C/аналоговый, по железу),
 - нормализацию/фильтрацию,
 - калибровку (минимум двухточечную) с хранением в NVS.
 3. Настроить MQTT-публикацию телеметрии для pH-ноды.
- Связанные документы:
 - `HARDWARE_ARCH_FULL.md`
 - `DEVICE_NODE_PROTOCOL.md`
 - `MQTT_SPEC_FULL.md`
 - `BACKEND_NODE_CONTRACT_FULL.md`
 - `ESP32_C_CODING_STANDARDS.md`

---

### 2.2. EC-нода (P0)

Аналогично pH-нODE, но с EC/температурой раствора.

---

### 2.3. Климат-нода (P1)

Сенсоры T/RH/CO₂/освещённость, публикация в MQTT, интеграция с зонами.

---

## 3. Backend: ядро и MQTT-интеграция

### 3.1. Полная реализация MQTT-контракта (P0)

**Цель:** backend корректно принимает телеметрию и статусы узлов, пишет их в БД.

- Тип задачи: «изменение backend/БД» + «изменение MQTT-спеки».
- Что сделать:
 1. Внедрить MQTT-клиент (Python/Php-worker) согласно `MQTT_SPEC_FULL.md` и `PYTHON_MQTT_SERVICE_AI_GUIDE.md`.
 2. Реализовать обработчики всех ключевых типов сообщений от узлов:
 - телеметрия (ph/ec/climate),
 - статусы узла,
 - регистрация/hello-сообщения.
 3. Привязать к данным:
 - `DeviceNode`,
 - `Zone`,
 - временные ряды.
- Связанные документы:
 - `MQTT_SPEC_FULL.md`
 - `BACKEND_NODE_CONTRACT_FULL.md`
 - `DATABASE_SCHEMA_AI_GUIDE.md`
 - `PYTHON_MQTT_SERVICE_AI_GUIDE.md`
 - `BACKEND_LARAVEL_PG_AI_GUIDE.md`

---

### 3.2. Реализация lifecycle узлов в backend (P0)

**Цель:** backend понимает состояния узлов (REGISTERED, ASSIGNED_TO_ZONE, ACTIVE, DEGRADED и т.п.).

- Тип задачи: backend/БД.
- Что сделать:
 1. Добавить/уточнить поля в модели `DeviceNode` (см. `NODE_LIFECYCLE_AND_PROVISIONING.md`).
 2. Реализовать обработку registration-сообщений от узлов.
 3. Реализовать API/панель для привязки узлов к зонам и замены нод.
- Связанные документы:
 - `NODE_LIFECYCLE_AND_PROVISIONING.md`
 - `DATA_MODEL_REFERENCE.md`
 - `BACKEND_ARCH_FULL.md`

---

## 4. Domain: рецепты, зоны, алерты

### 4.1. Engine зон и рецептов (P0)

**Цель:** рабочий контур «зона + рецепт» с вычислением целевых значений и выдачей команд.

- Тип задачи: backend-домен.
- Что сделать:
 1. Реализовать `ZoneController` согласно `ZONE_CONTROLLERS_AI_GUIDE.md`.
 2. Реализовать движок рецептов и стадий (`RECIPE_ENGINE_FULL.md`).
 3. Связать с фактами телеметрии от узлов.
- Связанные документы:
 - `ZONE_CONTROLLERS_AI_GUIDE.md`
 - `RECIPE_ENGINE_FULL.md`
 - `DATA_MODEL_REFERENCE.md`

---

### 4.2. Events & Alerts engine (P0)

**Цель:** автоматически генерировать алерты по зонам и узлам.

- Тип задачи: backend-домен.
- Что сделать:
 1. Реализовать правила алертов согласно `EVENTS_AND_ALERTS_ENGINE.md`.
 2. Интегрировать с историей измерений и текущими целевыми диапазонами.
 3. Подключить каналы доставки:
 - realtime (`REALTIME_UPDATES_ARCH.md`),
 - push (`ALERTS_AND_NOTIFICATIONS_CHANNELS.md`).
- Связанные документы:
 - `EVENTS_AND_ALERTS_ENGINE.md`
 - `REALTIME_UPDATES_ARCH.md`
 - `ALERTS_AND_NOTIFICATIONS_CHANNELS.md`

---

## 5. Frontend + Android

### 5.1. Web-дашборд MVP (P1)

**Цель:** фронт показывает теплицы, зоны, алерты в реальном времени.

- Тип задачи: frontend + realtime интеграция.
- Что сделать:
 1. Реализовать базовые экраны:
 - список теплиц,
 - список зон,
 - деталка зоны,
 - список алертов.
 2. Подключить WebSocket по `REALTIME_UPDATES_ARCH.md`.
 3. Подтягивать начальные данные по REST.
- Связанные документы:
 - `SYSTEM_ARCH_FULL.md`
 - `REALTIME_UPDATES_ARCH.md`
 - `API_SPEC_FRONTEND_BACKEND_FULL.md`

---

### 5.2. Android-приложение: provisioning + просмотр зон (P1)

**Цель:** телефон может:
- настроить узел (Wi-Fi),
- смотреть зоны и алерты.

- Тип задачи: Android.
- Что сделать:
 1. Реализовать provisioning-flow согласно:
 - `ANDROID_APP_ARCH.md`
 - `ANDROID_APP_SCREENS.md`
 - `ANDROID_APP_API_INTEGRATION.md`
 - `WIFI_PROVISIONING_FIRST_RUN.md`
 2. Реализовать:
 - логин,
 - список теплиц/зон,
 - просмотр алертов.
 3. Интеграция с realtime и push.
- Связанные документы:
 - `ANDROID_APP_*`
 - `REALTIME_UPDATES_ARCH.md`
 - `ALERTS_AND_NOTIFICATIONS_CHANNELS.md`

---

## 6. Security, Ops, тестирование

### 6.1. Настройка тестов и CI/CD (P1)

**Цель:** минимальный, но работающий контур тестов и CI.

- Тип задачи: архитектура тестирования.
- Что сделать:
 1. Для каждой части (firmware/backend/frontend/Android) завести базовый набор тестов.
 2. Настроить CI (GitHub Actions/GitLab CI) согласно `TESTING_AND_CICD_STRATEGY.md`.
- Связанные документы:
 - `TESTING_AND_CICD_STRATEGY.md`
 - `BACKUP_AND_RECOVERY.md`
 - `SYSTEM_FAILURE_RECOVERY.md`

---

## 7. Роль meta-агента

Meta-агент при планировании спринта:

1. Выбирает блок (например, «Firmware: pH-нода»).
2. Делит его на 2–5 задач по шаблонам из `AI_TASK_TEMPLATES_AND_PATTERNS.md`.
3. Для каждой задачи:
 - записывает краткое ТЗ в терминах этого файла,
 - прикладывает ссылки на все упомянутые .md.
4. После выполнения:
 - проверяет, что:
 - код/доки соответствуют архитектуре,
 - не нарушены контракты (MQTT/REST/WebSocket),
 - при необходимости обновлены связанные документы.

Этот файл должен регулярно обновляться по мере реализации задач:
- выполненные P0-пункты помечаются как DONE,
- добавляются новые P1/P2 по мере развития системы.
