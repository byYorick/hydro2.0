# Config Storage Component

Компонент для хранения и загрузки NodeConfig из NVS (Non-Volatile Storage).

## Описание

Компонент `config_storage` обеспечивает:
- Загрузку NodeConfig из NVS при старте узла
- Сохранение обновленного конфига в NVS
- API для доступа к параметрам конфигурации
- Валидацию конфигурации

## Использование

### Инициализация

```c
#include "config_storage.h"

// Инициализация компонента
esp_err_t err = config_storage_init();
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to initialize config storage");
    return;
}

// Загрузка конфигурации из NVS
err = config_storage_load();
if (err == ESP_ERR_NOT_FOUND) {
    ESP_LOGW(TAG, "No config in NVS, waiting for config from MQTT");
} else if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to load config: %s", esp_err_to_name(err));
}
```

### Получение параметров

```c
// Получение node_id
char node_id[64];
if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
    ESP_LOGI(TAG, "Node ID: %s", node_id);
}

// Получение параметров MQTT
config_storage_mqtt_t mqtt;
if (config_storage_get_mqtt(&mqtt) == ESP_OK) {
    ESP_LOGI(TAG, "MQTT host: %s:%d", mqtt.host, mqtt.port);
}

// Получение параметров Wi-Fi
config_storage_wifi_t wifi;
if (config_storage_get_wifi(&wifi) == ESP_OK) {
    ESP_LOGI(TAG, "Wi-Fi SSID: %s", wifi.ssid);
}
```

### Сохранение конфигурации

```c
// Валидация перед сохранением
char error_msg[128];
esp_err_t err = config_storage_validate(json_config, json_len, error_msg, sizeof(error_msg));
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Config validation failed: %s", error_msg);
    return;
}

// Сохранение в NVS
err = config_storage_save(json_config, json_len);
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to save config: %s", esp_err_to_name(err));
    return;
}
```

## Структура данных

### config_storage_mqtt_t

```c
typedef struct {
    char host[128];
    uint16_t port;
    uint16_t keepalive;
    char username[128];
    char password[128];
    bool use_tls;
} config_storage_mqtt_t;
```

### config_storage_wifi_t

```c
typedef struct {
    char ssid[128];
    char password[128];
    bool auto_reconnect;
    uint16_t timeout_sec;
} config_storage_wifi_t;
```

## NVS структура

- **Namespace:** `node_config`
- **Key:** `config`
- **Формат:** JSON строка
- **Максимальный размер:** 4096 байт

## Документация

- Спецификация NodeConfig: `../../../../NODE_CONFIG_SPEC.md`
- Архитектура нод: `../../../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`









