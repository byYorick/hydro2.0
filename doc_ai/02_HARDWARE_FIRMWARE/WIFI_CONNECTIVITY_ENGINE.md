# WIFI_CONNECTIVITY_ENGINE.md
# Wi-Fi connectivity runtime для ESP32-нод (2.0)
# Current implementation • constraints • production checklist

Документ фиксирует фактическое состояние Wi-Fi слоя в текущем production baseline.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Область и статус

Этот документ описывает:
- текущую реализацию `wifi_manager` в `firmware/nodes/common/components/wifi_manager/`;
- связь с provisioning (`setup_portal`) и NodeConfig (`config_storage`);
- ограничения runtime, которые надо учитывать при выводе real-node в боевой режим.

Важно:
- ранее описанная модульная архитектура (`wifi_scan`, `wifi_roaming`, `multi-ap`) является целевым планом;
- в текущем runtime она не реализована как отдельные компоненты.

---

# 2. Фактическая архитектура (runtime)

## 2.1. Основной компонент

Текущая реализация Wi-Fi находится в одном компоненте:
- `firmware/nodes/common/components/wifi_manager/wifi_manager.c`
- `firmware/nodes/common/components/wifi_manager/include/wifi_manager.h`

Функции:
- `wifi_manager_init()`
- `wifi_manager_connect()`
- `wifi_manager_disconnect()`
- `wifi_manager_is_connected()`
- `wifi_manager_get_rssi()`
- `wifi_manager_register_connection_cb()`
- `wifi_manager_deinit()`

## 2.2. Хранение конфигурации

Wi-Fi и MQTT параметры берутся из общего NodeConfig (`config_storage`), а не из отдельного `network` namespace:
- `wifi.ssid`, `wifi.pass`, `wifi.auto_reconnect`, `wifi.timeout_sec`
- `mqtt.host`, `mqtt.port`, `mqtt.keepalive`, `mqtt.username/password`, `mqtt.use_tls`

## 2.3. Provisioning

Первичная настройка выполняется через `setup_portal`:
- AP + HTTP (`GET /`, `POST /wifi/connect`);
- после успешного приёма данных обновляется NodeConfig и выполняется перезапуск.

Детали см. `WIFI_PROVISIONING_FIRST_RUN.md`.

---

# 3. Поведение подключения

## 3.1. connect flow

Базовый flow:
1. `wifi_manager_connect(config)` применяет SSID/password в `esp_wifi_set_config`.
2. Запускает `esp_wifi_connect()`.
3. Ждёт `WIFI_CONNECTED_BIT` или `WIFI_FAIL_BIT` в event group.
4. Возвращает `ESP_OK`/`ESP_FAIL`/`ESP_ERR_TIMEOUT`.

## 3.2. reconnect flow

Текущая логика reconnect:
- повторное подключение выполняется сразу в `WIFI_EVENT_STA_DISCONNECTED` через `esp_wifi_connect()`;
- без прогрессивного backoff;
- с лимитом `max_reconnect_attempts` (0 = безлимит).

Значения по умолчанию:
- `timeout_sec`: 30;
- `auto_reconnect`: `true`;
- `max_reconnect_attempts`: 5.

## 3.3. power save

В `wifi_manager_connect()` выставляется:
- `esp_wifi_set_ps(WIFI_PS_NONE)`.

То есть режимы `WIFI_PS_MIN_MODEM`/`Light Sleep` в текущем baseline не используются.

---

# 4. Интеграция с MQTT и статусами

- Wi-Fi компонент отдаёт состояние через callback `wifi_connection_cb_t`.
- Публикация MQTT `status` выполняется отдельным MQTT-слоем (`mqtt_manager`) и задачами нод.
- Для `status` в MQTT используется QoS 1 + retain=true.

Важно:
- нет отдельного публичного MQTT-потока "Wi-Fi events" (`WIFI_AUTH_FAIL`, `WIFI_CHANGED_AP` и т.п.) как стабильного контракта;
- часть диагностических полей (`ip`, `rssi`, `fw`) публикуется из node-specific задач.

---

# 5. Не реализовано в текущем runtime (tech debt)

Следующие возможности считаются целевыми, но сейчас отсутствуют как production-функции:
- Multi-AP с primary/backup SSID;
- roaming между BSSID;
- периодический scan engine и публикация таблицы AP;
- автоматический fail-safe уровня "отключить dosing/irrigation/heater после X минут offline";
- стандартный alarm `NODE_WIFI_UNSTABLE` как закреплённый runtime-контракт.

---

# 6. Ограничения для production rollout

1. Нельзя рассчитывать на автоматическое переключение на backup AP.
2. Нельзя рассчитывать на backoff reconnect; повторные попытки идут immediately.
3. Нельзя рассчитывать на отдельные Wi-Fi event payload в MQTT как на контракт.
4. Для setup portal сейчас принимается только IPv4-формат `mqtt_host` (не DNS hostname).

---

# 7. Чек-лист перед боевым запуском real-node

1. В NodeConfig заданы валидные `wifi.ssid/pass` и `mqtt.host/port`.
2. Проверен reconnect при кратковременном пропадании AP.
3. Проверен reconnect при рестарте MQTT broker.
4. Проверено, что после reconnect публикуются `status` и `heartbeat`.
5. Подтверждена корректная работа provisioning (`POST /wifi/connect`) на реальном устройстве.
6. Подтверждено отсутствие утечек/роста heap при длительном reconnect-цикле.

---

# 8. Требования к ИИ-агенту

1. Не документировать как runtime-факт функции, которых нет в коде (`multi-ap`, roaming, scan engine).
2. При добавлении Wi-Fi возможностей сначала обновлять этот документ и `WIFI_PROVISIONING_FIRST_RUN.md`.
3. Не менять контракт хранения NodeConfig без синхронизации с `NODE_CONFIG_SPEC.md`.

---

# Конец файла WIFI_CONNECTIVITY_ENGINE.md
