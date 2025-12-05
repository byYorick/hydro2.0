/**
 * @file relay_driver.c
 * @brief Реализация драйвера для управления реле
 * 
 * Компонент реализует управление оптоизолированными реле модулями через GPIO.
 * Поддерживает NC (Normaly-Closed) и NO (Normaly-Open) реле.
 */

#include "relay_driver.h"
#include "config_storage.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include "cJSON.h"

static const char *TAG = "relay_driver";

#define MAX_RELAY_CHANNELS 16
#define RELAY_DRIVER_MAX_STRING_LEN 64

/**
 * @brief Структура канала реле
 */
typedef struct {
    char channel_name[RELAY_DRIVER_MAX_STRING_LEN];
    int gpio_pin;
    relay_type_t relay_type;
    bool active_high;
    relay_state_t current_state;
    bool initialized;
} relay_channel_t;

static relay_channel_t s_channels[MAX_RELAY_CHANNELS] = {0};
static size_t s_channel_count = 0;
static bool s_initialized = false;
static SemaphoreHandle_t s_mutex = NULL;

static esp_err_t relay_driver_set_gpio_state(int gpio_pin, bool active, bool active_high) {
    int level = active ? (active_high ? 1 : 0) : (active_high ? 0 : 1);
    return gpio_set_level(gpio_pin, level);
}

esp_err_t relay_driver_init(const relay_channel_config_t *channels, size_t channel_count) {
    if (channels == NULL || channel_count == 0) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (channel_count > MAX_RELAY_CHANNELS) {
        ESP_LOGE(TAG, "Too many channels: %zu (max: %d)", channel_count, MAX_RELAY_CHANNELS);
        return ESP_ERR_INVALID_ARG;
    }
    
    if (s_initialized) {
        ESP_LOGW(TAG, "Relay driver already initialized");
        return ESP_OK;
    }
    
    // Создание mutex
    if (s_mutex == NULL) {
        s_mutex = xSemaphoreCreateMutex();
        if (s_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    
    // Инициализация GPIO
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = 0,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
    };
    
    // Собираем маску GPIO пинов
    for (size_t i = 0; i < channel_count; i++) {
        io_conf.pin_bit_mask |= (1ULL << channels[i].gpio_pin);
    }
    
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure GPIO: %s", esp_err_to_name(err));
        vSemaphoreDelete(s_mutex);
        s_mutex = NULL;
        return err;
    }
    
    // Инициализация каналов
    for (size_t i = 0; i < channel_count; i++) {
        relay_channel_t *channel = &s_channels[i];
        strncpy(channel->channel_name, channels[i].channel_name, sizeof(channel->channel_name) - 1);
        channel->channel_name[sizeof(channel->channel_name) - 1] = '\0';  // Гарантируем null-termination
        channel->gpio_pin = channels[i].gpio_pin;
        channel->relay_type = channels[i].relay_type;
        channel->active_high = channels[i].active_high;
        channel->current_state = RELAY_STATE_OPEN; // По умолчанию разомкнуто
        channel->initialized = true;
        
        // Устанавливаем начальное состояние (разомкнуто)
        relay_driver_set_gpio_state(channel->gpio_pin, false, channel->active_high);
        
        ESP_LOGI(TAG, "Initialized relay channel: %s, GPIO=%d, type=%s, active_high=%s",
                channel->channel_name, channel->gpio_pin,
                channel->relay_type == RELAY_TYPE_NC ? "NC" : "NO",
                channel->active_high ? "HIGH" : "LOW");
    }
    
    s_channel_count = channel_count;
    s_initialized = true;
    
    ESP_LOGI(TAG, "Relay driver initialized with %zu channels", channel_count);
    return ESP_OK;
}

esp_err_t relay_driver_init_from_config(void) {
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load config from storage");
        return err;
    }
    
    cJSON *config = cJSON_Parse(config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        return ESP_FAIL;
    }
    
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels == NULL || !cJSON_IsArray(channels)) {
        ESP_LOGE(TAG, "No channels array in config");
        cJSON_Delete(config);
        return ESP_ERR_NOT_FOUND;
    }
    
    relay_channel_config_t relay_configs[MAX_RELAY_CHANNELS];
    // ВАЖНО: Буферы для хранения имен каналов (нужны, так как JSON будет удален)
    static char channel_names[MAX_RELAY_CHANNELS][RELAY_DRIVER_MAX_STRING_LEN];
    size_t relay_count = 0;
    
    int channel_count = cJSON_GetArraySize(channels);
    for (int i = 0; i < channel_count && relay_count < MAX_RELAY_CHANNELS; i++) {
        cJSON *channel = cJSON_GetArrayItem(channels, i);
        if (channel == NULL || !cJSON_IsObject(channel)) {
            continue;
        }
        
        cJSON *type_item = cJSON_GetObjectItem(channel, "type");
        if (type_item == NULL || !cJSON_IsString(type_item)) {
            continue;
        }
        
        // Ищем только актуаторы типа RELAY
        if (strcmp(type_item->valuestring, "ACTUATOR") == 0) {
            cJSON *actuator_type = cJSON_GetObjectItem(channel, "actuator_type");
            if (actuator_type != NULL && cJSON_IsString(actuator_type)) {
                // Проверяем, является ли это реле
                const char *act_type = actuator_type->valuestring;
                if (strcmp(act_type, "RELAY") == 0 || strcmp(act_type, "FAN") == 0 || 
                    strcmp(act_type, "HEATER") == 0) {
                    cJSON *name_item = cJSON_GetObjectItem(channel, "name");
                    cJSON *gpio_item = cJSON_GetObjectItem(channel, "gpio");
                    cJSON *fail_safe_item = cJSON_GetObjectItem(channel, "fail_safe_mode");
                    
                    if (name_item != NULL && cJSON_IsString(name_item) &&
                        gpio_item != NULL && cJSON_IsNumber(gpio_item)) {
                        relay_channel_config_t *relay_cfg = &relay_configs[relay_count];
                        // Копируем имя канала в статический буфер перед удалением JSON
                        strncpy(channel_names[relay_count], name_item->valuestring, RELAY_DRIVER_MAX_STRING_LEN - 1);
                        channel_names[relay_count][RELAY_DRIVER_MAX_STRING_LEN - 1] = '\0';
                        relay_cfg->channel_name = channel_names[relay_count];
                        relay_cfg->gpio_pin = (int)cJSON_GetNumberValue(gpio_item);
                        relay_cfg->active_high = true; // По умолчанию active high
                        
                        // Определяем тип реле из fail_safe_mode или по умолчанию NO
                        if (fail_safe_item != NULL && cJSON_IsString(fail_safe_item)) {
                            if (strcmp(fail_safe_item->valuestring, "NC") == 0) {
                                relay_cfg->relay_type = RELAY_TYPE_NC;
                            } else {
                                relay_cfg->relay_type = RELAY_TYPE_NO;
                            }
                        } else {
                            relay_cfg->relay_type = RELAY_TYPE_NO;
                        }
                        
                        relay_count++;
                    }
                }
            }
        }
    }
    
    cJSON_Delete(config);
    
    if (relay_count == 0) {
        ESP_LOGW(TAG, "No relay channels found in config");
        return ESP_ERR_NOT_FOUND;
    }
    
    return relay_driver_init(relay_configs, relay_count);
}

esp_err_t relay_driver_deinit(void) {
    if (!s_initialized) {
        return ESP_OK;
    }
    
    // Устанавливаем все реле в безопасное состояние (разомкнуто)
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized) {
            relay_driver_set_gpio_state(s_channels[i].gpio_pin, false, s_channels[i].active_high);
        }
    }
    
    if (s_mutex != NULL) {
        vSemaphoreDelete(s_mutex);
        s_mutex = NULL;
    }
    
    memset(s_channels, 0, sizeof(s_channels));
    s_channel_count = 0;
    s_initialized = false;
    
    ESP_LOGI(TAG, "Relay driver deinitialized");
    return ESP_OK;
}

esp_err_t relay_driver_set_state(const char *channel_name, relay_state_t state) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Relay driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (channel_name == NULL) {
        ESP_LOGE(TAG, "Invalid channel name");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex");
        return ESP_ERR_TIMEOUT;
    }
    
    // Поиск канала
    relay_channel_t *channel = NULL;
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && 
            strcmp(s_channels[i].channel_name, channel_name) == 0) {
            channel = &s_channels[i];
            break;
        }
    }
    
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Channel not found: %s", channel_name);
        return ESP_ERR_NOT_FOUND;
    }
    
    // Установка состояния GPIO
    // Для CLOSED: активный уровень, для OPEN: неактивный
    bool gpio_active = (state == RELAY_STATE_CLOSED);
    esp_err_t err = relay_driver_set_gpio_state(channel->gpio_pin, gpio_active, channel->active_high);
    
    if (err == ESP_OK) {
        channel->current_state = state;
        ESP_LOGI(TAG, "Relay channel %s set to %s (GPIO=%d, level=%d)",
                channel_name, state == RELAY_STATE_CLOSED ? "CLOSED" : "OPEN",
                channel->gpio_pin, gpio_active ? 1 : 0);
    }
    
    xSemaphoreGive(s_mutex);
    return err;
}

esp_err_t relay_driver_get_state(const char *channel_name, relay_state_t *state) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Relay driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (channel_name == NULL || state == NULL) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex");
        return ESP_ERR_TIMEOUT;
    }
    
    // Поиск канала
    relay_channel_t *channel = NULL;
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && 
            strcmp(s_channels[i].channel_name, channel_name) == 0) {
            channel = &s_channels[i];
            break;
        }
    }
    
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Channel not found: %s", channel_name);
        return ESP_ERR_NOT_FOUND;
    }
    
    *state = channel->current_state;
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

bool relay_driver_is_initialized(void) {
    return s_initialized;
}

