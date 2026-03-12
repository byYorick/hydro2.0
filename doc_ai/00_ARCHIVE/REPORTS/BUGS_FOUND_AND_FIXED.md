# Отчет о найденных и исправленных багах

**Дата:** 2025-01-27  
**Статус:** Исправлено

---

## Критические баги

### 1. DEADLOCK в `pump_driver_emergency_stop()` ⚠️ КРИТИЧНО

**Файл:** `firmware/nodes/common/components/pump_driver/pump_driver.c`

**Проблема:**
Функция `pump_driver_emergency_stop()` захватывает mutex, а затем вызывает `pump_stop_internal()`, который также пытается захватить тот же mutex. Это приводит к deadlock (взаимной блокировке).

**Код с багом:**
```c
esp_err_t pump_driver_emergency_stop(void) {
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && s_channels[i].is_running) {
            pump_stop_internal(s_channels[i].channel_name);  // ❌ DEADLOCK: пытается взять mutex снова
        }
    }
    
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}
```

**Исправление:**
Создана версия `pump_stop_internal_unlocked()` которая не захватывает mutex (предполагает, что mutex уже взят). Функция `pump_driver_emergency_stop()` теперь использует эту версию.

**Исправленный код:**
```c
// Внутренняя версия остановки без захвата mutex
static esp_err_t pump_stop_internal_unlocked(pump_channel_t *channel) {
    // ... логика остановки без mutex ...
}

esp_err_t pump_driver_emergency_stop(void) {
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && s_channels[i].is_running) {
            pump_stop_internal_unlocked(&s_channels[i]);  // ✅ Использует версию без mutex
        }
    }
    
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}
```

**Последствия:**
- Без исправления: система зависает при вызове `pump_driver_emergency_stop()` (например, при переходе в safe_mode)
- После исправления: функция работает корректно, все насосы останавливаются

---

### 2. Отсутствие обработки ошибки памяти в `node_command_handler.c` ⚠️ ВАЖНО

**Файл:** `firmware/nodes/common/components/node_framework/node_command_handler.c`

**Проблема:**
Если `cJSON_Duplicate()` возвращает `NULL` (нехватка памяти), код не обрабатывает эту ошибку и продолжает выполнение, что может привести к проблемам.

**Код с багом:**
```c
cJSON *params = cJSON_Duplicate(json, 1);
if (params) {
    // ... обработка ...
}  // ❌ Если params == NULL, ответ не создается, команда "теряется"
```

**Исправление:**
Добавлена обработка случая, когда `cJSON_Duplicate()` возвращает `NULL`. В этом случае создается ответ об ошибке.

**Исправленный код:**
```c
cJSON *params = cJSON_Duplicate(json, 1);
if (params == NULL) {
    ESP_LOGE(TAG, "Failed to duplicate command JSON (out of memory)");
    response = node_command_handler_create_response(
        cmd_id,
        "ERROR",
        "memory_error",
        "Failed to parse command parameters",
        NULL
    );
} else {
    // ... обработка ...
}
```

**Последствия:**
- Без исправления: при нехватке памяти команда не обрабатывается и не отправляется ответ
- После исправления: отправляется ответ об ошибке, система продолжает работать

---

## Проверенные места без проблем

### 3. Вызовы `pump_stop_internal()` из других мест

Проверены все вызовы `pump_stop_internal()`:
- ✅ `pump_driver_stop()` - mutex не взят, вызов корректен
- ✅ `pump_timer_callback()` - mutex не взят, вызов корректен
- ✅ Вызов из `pump_start_internal()` при ошибке - mutex не взят, вызов корректен

Все эти вызовы безопасны, так как mutex не захвачен в момент вызова.

---

## Рекомендации

1. **Проверка на deadlock:**
   - При рефакторинге функций, которые работают с mutex, проверять все вложенные вызовы
   - Использовать статический анализ кода для поиска потенциальных deadlock

2. **Обработка ошибок памяти:**
   - Всегда проверять возвращаемые значения функций выделения памяти (`malloc`, `cJSON_Duplicate`, и т.д.)
   - Создавать ответы об ошибках при нехватке памяти

3. **Тестирование:**
   - Добавить unit-тесты для проверки `pump_driver_emergency_stop()` на deadlock
   - Добавить тесты для обработки ошибок памяти в обработчиках команд

---

---

### 3. Отсутствие null-termination после `strncpy()` в `pump_driver.c` ⚠️ ВАЖНО

**Файл:** `firmware/nodes/common/components/pump_driver/pump_driver.c`

**Проблема:**
Функция `strncpy()` не гарантирует null-termination, если исходная строка длиннее, чем размер буфера - 1. Это может привести к переполнению буфера или чтению мусора при последующем использовании строк.

**Места с багом:**
1. Строка 148: `strncpy(channel->channel_name, ...)`
2. Строка 152: `strncpy(channel->relay_channel, ...)`
3. Строка 818: `strncpy(out->channel_name, ...)`

**Код с багом:**
```c
strncpy(channel->channel_name, channels[i].channel_name, sizeof(channel->channel_name) - 1);
// ❌ Если исходная строка длиннее, null-terminator не установлен
```

**Исправление:**
Добавлена явная установка `'\0'` в конце строки после каждого `strncpy()`.

**Исправленный код:**
```c
strncpy(channel->channel_name, channels[i].channel_name, sizeof(channel->channel_name) - 1);
channel->channel_name[sizeof(channel->channel_name) - 1] = '\0';  // ✅ Гарантируем null-termination
```

**Последствия:**
- Без исправления: потенциальное переполнение буфера или чтение мусора при использовании строк
- После исправления: строки всегда корректно завершаются null-terminator

**Примечание:**
В других файлах (`node_command_handler.c`, `node_telemetry_engine.c`) эта проблема уже была исправлена ранее.

---

**Статус:** ✅ Все критические и важные баги исправлены

