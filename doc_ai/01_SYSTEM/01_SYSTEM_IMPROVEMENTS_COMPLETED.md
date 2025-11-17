# Выполненные доработки 01_SYSTEM

**Дата выполнения:** 2025-11-17  
**Основа:** План доработок на основе аудита `AUDIT_GAPS.md`

---

## Резюме

Выполнены критические компоненты из аудита папки `01_SYSTEM`:
- ✅ Жизненный цикл узлов (lifecycle_state, hardware_id, node_hello)
- ✅ Config Flow — публикация и автоматическая синхронизация NodeConfig
- ✅ Heartbeat Flow — обработка heartbeat сообщений
- ✅ Замена узлов — API и логика замены узлов

---

## 1. Жизненный цикл узлов

### 1.1. Расширение модели данных

**Файлы:**
- `backend/laravel/database/migrations/2025_11_17_174432_add_lifecycle_to_nodes_table.php`
- `backend/laravel/app/Enums/NodeLifecycleState.php`
- `backend/laravel/app/Models/DeviceNode.php`

**Реализовано:**
- ✅ Добавлено поле `lifecycle_state` (string, default: 'UNPROVISIONED') в таблицу `nodes`
- ✅ Добавлено поле `hardware_id` (string, nullable, unique) в таблицу `nodes`
- ✅ Создан Enum `NodeLifecycleState` со значениями:
  - MANUFACTURED, UNPROVISIONED, PROVISIONED_WIFI, REGISTERED_BACKEND, ASSIGNED_TO_ZONE, ACTIVE, DEGRADED, MAINTENANCE, DECOMMISSIONED
- ✅ Обновлена модель `DeviceNode`:
  - Добавлены поля `lifecycle_state` и `hardware_id`
  - Добавлены методы для работы с состояниями (`canReceiveTelemetry()`, `isActive()`, и т.д.)
  - Добавлены методы переходов между состояниями

**Статус:** ✅ **MVP_DONE**

---

### 1.2. NodeLifecycleService

**Файлы:**
- `backend/laravel/app/Services/NodeLifecycleService.php`

**Реализовано:**
- ✅ Сервис для управления переходами между состояниями жизненного цикла
- ✅ Валидация разрешённых переходов между состояниями
- ✅ Методы для каждого типа перехода (`transitionToProvisioned()`, `transitionToActive()`, и т.д.)
- ✅ Логирование всех переходов состояний

**Статус:** ✅ **MVP_DONE**

---

### 1.3. Обработка node_hello

**Файлы:**
- `backend/services/history-logger/main.py`
- `backend/laravel/app/Services/NodeRegistryService.php`
- `backend/laravel/app/Http/Controllers/NodeController.php`

**Реализовано:**
- ✅ Обработчик `handle_node_hello()` в `history-logger`
- ✅ Подписка на топики `hydro/node_hello` и `hydro/+/+/+/node_hello`
- ✅ Интеграция с Laravel API `/api/nodes/register`
- ✅ Метод `registerNodeFromHello()` в `NodeRegistryService`:
  - Поиск узла по `hardware_id`
  - Генерация `uid` на основе `hardware_id` и типа узла
  - Обработка `greenhouse_token` для привязки к теплице
  - Автоматический переход в состояние `REGISTERED_BACKEND` или `ASSIGNED_TO_ZONE`

**Статус:** ✅ **MVP_DONE**

---

## 2. Config Flow — публикация NodeConfig

### 2.1. NodeConfigService

**Файлы:**
- `backend/laravel/app/Services/NodeConfigService.php`

**Реализовано:**
- ✅ Сервис для генерации полного NodeConfig из данных БД
- ✅ Формирование `channels` из таблицы `node_channels`
- ✅ Генерация `wifi` и `mqtt` конфигурации
- ✅ Нормализация типов каналов (SENSOR/ACTUATOR)
- ✅ Автоматическое определение типа актуатора по имени канала
- ✅ Валидация конфига перед возвратом

**Статус:** ✅ **MVP_DONE**

---

### 2.2. Публикация NodeConfig через MQTT

**Файлы:**
- `backend/services/mqtt-bridge/publisher.py`
- `backend/services/mqtt-bridge/main.py`
- `backend/laravel/app/Http/Controllers/NodeController.php`

**Реализовано:**
- ✅ Метод `publish_config()` в `Publisher`
- ✅ Endpoint `/bridge/nodes/{node_uid}/config` в `mqtt-bridge`
- ✅ API методы `getConfig()` и `publishConfig()` в `NodeController`
- ✅ Роуты:
  - `GET /api/nodes/{node}/config` — получить конфиг
  - `POST /api/nodes/{node}/config/publish` — опубликовать конфиг

**Статус:** ✅ **MVP_DONE**

---

### 2.3. Автоматическая синхронизация NodeConfig

**Файлы:**
- `backend/laravel/app/Events/NodeConfigUpdated.php`
- `backend/laravel/app/Listeners/PublishNodeConfigOnUpdate.php`
- `backend/laravel/app/Models/DeviceNode.php`
- `backend/laravel/app/Models/NodeChannel.php`
- `backend/laravel/app/Providers/AppServiceProvider.php`

**Реализовано:**
- ✅ Event `NodeConfigUpdated` для уведомления об изменении конфига
- ✅ Listener `PublishNodeConfigOnUpdate` для автоматической публикации
- ✅ Регистрация слушателя в `AppServiceProvider`
- ✅ Автоматическая отправка события при изменении:
  - Узла (поля `zone_id`, `type`, `config`, `uid`)
  - Каналов узла (создание, обновление, удаление)
- ✅ Проверка состояния узла перед публикацией (только для узлов, которые могут принимать телеметрию)

**Статус:** ✅ **MVP_DONE**

---

## 3. Heartbeat Flow

### 3.1. Расширение модели данных

**Файлы:**
- `backend/laravel/database/migrations/2025_11_17_175127_add_heartbeat_to_nodes_table.php`
- `backend/laravel/app/Models/DeviceNode.php`

**Реализовано:**
- ✅ Добавлены поля в таблицу `nodes`:
  - `last_heartbeat_at` (timestamp, nullable)
  - `uptime_seconds` (integer, nullable) — время работы узла в секундах
  - `free_heap_bytes` (integer, nullable) — свободная память в байтах
  - `rssi` (integer, nullable) — сила сигнала Wi-Fi в dBm
- ✅ Обновлена модель `DeviceNode` для поддержки новых полей

**Статус:** ✅ **MVP_DONE**

---

### 3.2. Обработка heartbeat

**Файлы:**
- `backend/services/history-logger/main.py`

**Реализовано:**
- ✅ Обработчик `handle_heartbeat()` в `history-logger`
- ✅ Подписка на топик `hydro/+/+/+/heartbeat`
- ✅ Обновление полей `last_heartbeat_at`, `uptime_seconds`, `free_heap_bytes`, `rssi` в таблице `nodes`
- ✅ Обновление `last_seen_at` при получении heartbeat
- ✅ Метрика Prometheus `heartbeat_received_total` для мониторинга

**Статус:** ✅ **MVP_DONE**

---

## 4. Замена узлов

### 4.1. NodeSwapService

**Файлы:**
- `backend/laravel/app/Services/NodeSwapService.php`

**Реализовано:**
- ✅ Сервис для замены узла новым узлом
- ✅ Метод `swapNode()`:
  - Поиск старого узла по ID
  - Поиск/создание нового узла по `hardware_id`
  - Перепривязка `zone_id` и каналов (опционально)
  - Миграция истории телеметрии (опционально)
  - Помечание старого узла как `DECOMMISSIONED`
- ✅ Генерация нового `uid` для заменённого узла

**Статус:** ✅ **MVP_DONE**

---

### 4.2. API для замены узлов

**Файлы:**
- `backend/laravel/app/Http/Controllers/NodeController.php`
- `backend/laravel/routes/api.php`

**Реализовано:**
- ✅ Метод `swap()` в `NodeController`
- ✅ Endpoint `POST /api/nodes/{node}/swap`
- ✅ Валидация входных данных:
  - `new_hardware_id` (обязательно)
  - `migrate_telemetry` (опционально, по умолчанию false)
  - `migrate_channels` (опционально, по умолчанию true)

**Статус:** ✅ **MVP_DONE**

---

## Итоги

### Выполненные компоненты

1. ✅ **Жизненный цикл узлов:**
   - Расширение модели данных (lifecycle_state, hardware_id)
   - Enum NodeLifecycleState
   - NodeLifecycleService с валидацией переходов
   - Обработка node_hello в history-logger

2. ✅ **Config Flow:**
   - NodeConfigService для генерации конфига
   - Публикация NodeConfig через MQTT
   - Автоматическая синхронизация при изменениях

3. ✅ **Heartbeat Flow:**
   - Расширение модели данных (heartbeat метрики)
   - Обработка heartbeat в history-logger
   - Метрики Prometheus

4. ✅ **Замена узлов:**
   - NodeSwapService с поддержкой миграции
   - API endpoint для замены узлов

### Статус

**✅ Все компоненты высокого и среднего приоритета реализованы**

Система теперь поддерживает:
- Полный жизненный цикл узлов с автоматической регистрацией через MQTT
- Автоматическую синхронизацию NodeConfig при изменениях
- Мониторинг heartbeat узлов
- Замену узлов с сохранением истории

---

## Следующие шаги

### Рекомендуемые улучшения

1. **Структура проекта** (низкий приоритет):
   - Реорганизация backend сервисов с `src/` и `tests/`
   - Создание `backend/libs/` для общих библиотек

2. **Tools** (низкий приоритет):
   - Добавить `tools/stress_test_scenarios/` для нагрузочного тестирования

3. **Явная публикация status** (средний приоритет):
   - Реализовать публикацию `status` топика от узлов при подключении (в дополнение к LWT)

---

**Дата завершения:** 2025-11-17

