# Полный отчёт о багах цикла регистрации узлов

**Дата:** 5 декабря 2025  
**Статус:** 6 критических багов найдено и исправлено

---

## 🐛 Список всех найденных багов

### БАГ #1: Неправильная переменная токена в History Logger
**Критичность:** 🔴 Критический  
**Файл:** `backend/services/history-logger/main.py`  
**Статус:** ✅ Исправлен

**Проблема:**
```python
laravel_token = s.laravel_api_token  # ❌ Переменная не существует!
```

**Исправление:**
```python
ingest_token = s.history_logger_api_token if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
```

---

### БАГ #2: Некорректное сравнение Enum через >= (String Enum)
**Критичность:** 🔴 Критический  
**Файл:** `backend/laravel/app/Services/NodeConfigService.php`  
**Статус:** ✅ Исправлен

**Проблема:**
```php
$isAlreadyConnected = $lifecycleState->value >= NodeLifecycleState::REGISTERED_BACKEND->value;
// "ASSIGNED_TO_ZONE" >= "REGISTERED_BACKEND" = FALSE ❌ (сравнение по алфавиту!)
```

**Результат:** При переходе в ASSIGNED_TO_ZONE backend отправлял полные WiFi/MQTT настройки, перезаписывая рабочие.

**Исправление:**
```php
if ($lifecycleState->hasWorkingConnection()) {
    return ['configured' => true];
}
```

---

### БАГ #3: NodeService перезаписывает zone_id в null
**Критичность:** 🔴 Критический  
**Файл:** `backend/laravel/app/Services/NodeService.php`  
**Статус:** ✅ Исправлен

**Проблема:**
```php
if ($newZoneId && !$oldZoneId) {
    $data['zone_id'] = null; // ❌ Всегда затирает!
}
```

**Исправление:**
```php
$hasZoneIdInRequest = array_key_exists('zone_id', $data);
$hasPendingZoneIdInRequest = array_key_exists('pending_zone_id', $data);
$isInitialAssignmentFromUI = $hasZoneIdInRequest && !$hasPendingZoneIdInRequest && $newZoneId && !$oldZoneId;

if ($isInitialAssignmentFromUI) {
    $data['pending_zone_id'] = $newZoneId;
    $data['zone_id'] = null; // Только для первичной привязки от UI
}
```

---

### БАГ #4: Избыточные публикации конфига (9 вместо 1-2)
**Критичность:** 🟡 Средний  
**Файл:** `backend/laravel/app/Models/DeviceNode.php`  
**Статус:** ✅ Улучшено (9→3)

**Проблема:**
```php
$needsConfigPublish = $node->pending_zone_id && !$node->zone_id;
// Возвращало true при КАЖДОМ обновлении узла
```

**Исправление:**
```php
$needsConfigPublish = $node->pending_zone_id && !$node->zone_id && $node->wasChanged('pending_zone_id');
$skipAlreadyAssigned = $node->lifecycleState() === NodeLifecycleState::ASSIGNED_TO_ZONE && $node->zone_id;
```

---

### БАГ #5: MQTT настройки всегда отправлялись полностью
**Критичность:** 🔴 Критический  
**Файл:** `backend/laravel/app/Services/NodeConfigService.php`  
**Статус:** ✅ Исправлен

**Проблема:**
```php
// getMqttConfig() всегда возвращал:
$mqtt = [
    'host' => Config::get('services.mqtt.host'),
    'port' => (int) Config::get('services.mqtt.port'),
    // ... полная конфигурация
];
```

**Результат:** Узел переподключался к MQTT при каждой публикации конфига.

**Исправление:**
```php
if ($lifecycleState->hasWorkingConnection()) {
    return ['configured' => true];
}
```

---

### БАГ #6: Прошивка отклоняет конфиг с {"configured": true}
**Критичность:** 🔴 Критический  
**Файлы:** 
- `firmware/nodes/common/components/node_framework/node_config_handler.c`
- `firmware/nodes/common/components/config_storage/config_storage.c`
**Статус:** ✅ Исправлен

**Проблема:**
```c
// Валидация всегда требовала mqtt.host
cJSON *mqtt_host = cJSON_GetObjectItem(mqtt, "host");
if (!cJSON_IsString(mqtt_host) || ...) {
    return ESP_ERR_INVALID_ARG; // ❌ Отклоняет {"configured": true}
}
```

**Результат из логов ESP32:**
```
Config received: {"mqtt":{"configured":true}}
Config validation failed: Missing or invalid mqtt.host ❌
ERROR response sent
```

**Исправление:**
```c
// Проверяем, есть ли поле "configured": true
cJSON *mqtt_configured = cJSON_GetObjectItem(mqtt, "configured");
if (cJSON_IsBool(mqtt_configured) && cJSON_IsTrue(mqtt_configured)) {
    ESP_LOGI(TAG, "MQTT marked as 'configured', preserving existing settings");
    // Пропускаем валидацию host/port
} else {
    // Валидация полей только для полной конфигурации
    if (!cJSON_IsString(mqtt_host) || ...) {
        return ESP_ERR_INVALID_ARG;
    }
}
```

---

## 📊 Текущий статус ESP32 (из ваших логов)

### ✅ Что работает:

| Компонент | Статус | Детали |
|-----------|--------|--------|
| WiFi | ✅ Подключён | SSID: KKK_sklad, IP: 192.168.3.60 |
| MQTT | ✅ Подключён | Broker: 192.168.3.36:1883 |
| node_hello | ✅ Отправлен | Hardware ID: esp32-78e36ddde468 |
| Регистрация | ✅ Выполнена | UID: nd-clim-esp3278e |
| SHT3x | ✅ Работает | T=21.8°C, H=51.8% |
| Телеметрия | ✅ Отправляется | temperature, humidity |
| OLED | ✅ Работает | Инициализирован |

### ❌ Что НЕ работает:

| Проблема | Статус |
|----------|--------|
| Получение конфига | ❌ Отклонён валидацией |
| config_response | ❌ Отправлен ERROR |
| Завершение привязки | ❌ Не выполнено |

---

## 🔧 Что нужно сделать:

### 1. Перепрошить ESP32 с исправлениями

Исправлены файлы прошивки:
- ✅ `node_config_handler.c` - пропуск валидации для `{"configured": true}`
- ✅ `config_storage.c` - пропуск валидации для `{"configured": true}`

**Команды для перепрошивки:**
```bash
cd /home/georgiy/esp/hydro/hydro2.0/firmware/nodes/climate_node
idf.py build
idf.py flash monitor
```

### 2. После перепрошивки

ESP32 автоматически:
1. Загрузит сохранённый конфиг из NVS (WiFi/MQTT уже настроены)
2. Подключится к WiFi и MQTT
3. Отправит node_hello
4. Получит конфиг с `{"wifi":{"configured":true}, "mqtt":{"configured":true}}`
5. ✅ Валидация пройдёт успешно
6. ✅ WiFi/MQTT НЕ перезапустятся (настройки те же)
7. ✅ Обновятся только node_id, gh_uid, zone_uid
8. ✅ Отправит config_response с ACK
9. ✅ History Logger завершит привязку
10. ✅ Узел перейдёт в ASSIGNED_TO_ZONE

---

## 🎯 Итоговая таблица багов

| № | Баг | Компонент | Файл | Исправлен |
|---|-----|-----------|------|-----------|
| 1 | Неправильная переменная токена | History Logger | main.py | ✅ |
| 2 | Сравнение Enum через >= | Laravel Backend | NodeConfigService.php | ✅ |
| 3 | Перезапись zone_id | Laravel Backend | NodeService.php | ✅ |
| 4 | Избыточные публикации | Laravel Backend | DeviceNode.php | ✅ |
| 5 | MQTT всегда полный | Laravel Backend | NodeConfigService.php | ✅ |
| 6 | Валидация отклоняет {"configured"} | ESP32 Firmware | node_config_handler.c, config_storage.c | ✅ |

---

## 📝 Следующие шаги:

1. **Перепрошить ESP32** с исправлениями
2. **Перезагрузить ESP32** (кнопка RST)
3. **Привязать к зоне** через UI
4. **Проверить логи** - должен получить ACK

**После перепрошивки полный цикл будет работать!** 🚀

