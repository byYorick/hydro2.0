/**
 * @file pump_driver.c
 * @brief Реализация драйвера для управления насосами
 * 
 * Компонент реализует управление насосами через GPIO/MOSFET или через реле.
 * Поддерживает NC (Normaly-Closed) и NO (Normaly-Open) реле.
 */

#include "pump_driver.h"
#include "relay_driver.h"
#include "config_storage.h"
#include "ina209.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include <string.h>
#include "cJSON.h"

static const char *TAG = "pump_driver";

typedef struct {
    uint64_t total_run_time_ms;
    uint32_t last_run_duration_ms;
    uint32_t run_count;
    uint32_t failure_count;
    uint32_t overcurrent_events;
    uint32_t no_current_events;
    uint64_t last_start_timestamp_ms;
    uint64_t last_stop_timestamp_ms;
    bool last_run_success;
} pump_channel_stats_t;

/**
 * @brief Структура канала насоса
 */
typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    int gpio_pin;
    bool use_relay;
    char relay_channel[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    bool fail_safe_nc;
    uint32_t max_duration_ms;
    uint32_t min_off_time_ms;
    float ml_per_second;
    pump_driver_state_t current_state;
    bool is_running;
    uint64_t start_time_ms;
    uint32_t run_duration_ms;
    uint64_t last_stop_time_ms;
    TimerHandle_t timer;
    bool initialized;
    pump_channel_stats_t stats;
    bool last_command_success;
} pump_channel_t;

static pump_channel_t s_channels[PUMP_DRIVER_MAX_CHANNELS] = {0};
static size_t s_channel_count = 0;
static bool s_initialized = false;
static SemaphoreHandle_t s_mutex = NULL;
static ina209_config_t s_ina209_config = {0};
static bool s_ina209_enabled = false;
static uint32_t s_stabilization_delay_ms = 200; // Задержка стабилизации тока после включения насоса
static pump_driver_ina_status_t s_ina_status = {0};

// Forward declarations
static void pump_timer_callback(TimerHandle_t timer);
static esp_err_t pump_start_internal(const char *channel_name, uint32_t duration_ms);
static esp_err_t pump_stop_internal(const char *channel_name);
static pump_channel_t *find_channel(const char *channel_name);
static void pump_record_failure(pump_channel_t *channel);
static void pump_record_overcurrent(pump_channel_t *channel, bool undercurrent);
static void pump_fill_channel_health(const pump_channel_t *channel, pump_driver_channel_health_t *out);

static esp_err_t pump_set_gpio_state(pump_channel_t *channel, bool on) {
    if (channel->use_relay) {
        // Управление через реле
        relay_state_t relay_state = on ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
        // Для NC-реле: CLOSED = насос ON, OPEN = насос OFF
        // Для NO-реле: CLOSED = насос ON, OPEN = насос OFF
        return relay_driver_set_state(channel->relay_channel, relay_state);
    } else {
        // Прямое управление через GPIO/MOSFET
        // HIGH = насос включен (MOSFET открыт)
        int level = on ? 1 : 0;
        return gpio_set_level(channel->gpio_pin, level);
    }
}

esp_err_t pump_driver_init(const pump_channel_config_t *channels, size_t channel_count) {
    if (channels == NULL || channel_count == 0) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }

    if (channel_count > PUMP_DRIVER_MAX_CHANNELS) {
        ESP_LOGE(TAG, "Too many channels: %zu (max: %d)", channel_count, PUMP_DRIVER_MAX_CHANNELS);
        return ESP_ERR_INVALID_ARG;
    }
    
    if (s_initialized) {
        ESP_LOGW(TAG, "Pump driver already initialized");
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
    
    // Инициализация GPIO для каналов без реле
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = 0,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
    };
    
    // Собираем маску GPIO пинов для прямого управления
    for (size_t i = 0; i < channel_count; i++) {
        if (!channels[i].use_relay) {
            io_conf.pin_bit_mask |= (1ULL << channels[i].gpio_pin);
        }
    }
    
    if (io_conf.pin_bit_mask != 0) {
        esp_err_t err = gpio_config(&io_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure GPIO: %s", esp_err_to_name(err));
            vSemaphoreDelete(s_mutex);
            s_mutex = NULL;
            return err;
        }
    }
    
    // Инициализация каналов
    for (size_t i = 0; i < channel_count; i++) {
        pump_channel_t *channel = &s_channels[i];
        strncpy(channel->channel_name, channels[i].channel_name, sizeof(channel->channel_name) - 1);
        channel->gpio_pin = channels[i].gpio_pin;
        channel->use_relay = channels[i].use_relay;
        if (channels[i].use_relay && channels[i].relay_channel != NULL) {
            strncpy(channel->relay_channel, channels[i].relay_channel, sizeof(channel->relay_channel) - 1);
        }
        channel->fail_safe_nc = channels[i].fail_safe_nc;
        channel->max_duration_ms = channels[i].max_duration_ms;
        channel->min_off_time_ms = channels[i].min_off_time_ms;
        channel->ml_per_second = channels[i].ml_per_second;
        channel->current_state = PUMP_STATE_OFF;
        channel->is_running = false;
        channel->start_time_ms = 0;
        channel->run_duration_ms = 0;
        channel->last_stop_time_ms = 0;
        channel->initialized = true;
        memset(&channel->stats, 0, sizeof(channel->stats));
        channel->last_command_success = false;
        
        // Устанавливаем начальное состояние (выключено)
        pump_set_gpio_state(channel, false);
        
        // Создание таймера для автоостановки
        char timer_name[32];
        int name_len = snprintf(timer_name, sizeof(timer_name), "pump_%.*s", 
                                (int)(sizeof(timer_name) - 6), channel->channel_name);
        if (name_len < 0 || name_len >= (int)sizeof(timer_name)) {
            timer_name[sizeof(timer_name) - 1] = '\0';
        }
        channel->timer = xTimerCreate(timer_name, pdMS_TO_TICKS(1000), 
                                     pdFALSE, (void *)(uintptr_t)i, 
                                     pump_timer_callback);
        
        if (channel->timer == NULL) {
            ESP_LOGE(TAG, "Failed to create timer for channel %s", channel->channel_name);
            vSemaphoreDelete(s_mutex);
            s_mutex = NULL;
            return ESP_ERR_NO_MEM;
        }
        
        ESP_LOGI(TAG, "Initialized pump channel: %s, GPIO=%d, relay=%s, fail_safe=%s, max_duration=%lu ms",
                channel->channel_name, channel->gpio_pin,
                channel->use_relay ? channel->relay_channel : "direct",
                channel->fail_safe_nc ? "NC" : "NO",
                (unsigned long)channel->max_duration_ms);
    }
    
    s_channel_count = channel_count;
    s_initialized = true;

    ESP_LOGI(TAG, "Pump driver initialized with %zu channels", channel_count);
    return ESP_OK;
}

esp_err_t pump_driver_init_from_config(void) {
    char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
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
    
    pump_channel_config_t pump_configs[PUMP_DRIVER_MAX_CHANNELS];
    size_t pump_count = 0;

    int channel_count = cJSON_GetArraySize(channels);
    for (int i = 0; i < channel_count && pump_count < PUMP_DRIVER_MAX_CHANNELS; i++) {
        cJSON *channel = cJSON_GetArrayItem(channels, i);
        if (channel == NULL || !cJSON_IsObject(channel)) {
            continue;
        }
        
        cJSON *type_item = cJSON_GetObjectItem(channel, "type");
        if (type_item == NULL || !cJSON_IsString(type_item)) {
            continue;
        }
        
        // Ищем только актуаторы типа PUMP
        if (strcmp(type_item->valuestring, "ACTUATOR") == 0) {
            cJSON *actuator_type = cJSON_GetObjectItem(channel, "actuator_type");
            if (actuator_type != NULL && cJSON_IsString(actuator_type)) {
                const char *act_type = actuator_type->valuestring;
                if (strcmp(act_type, "PUMP") == 0) {
                    cJSON *name_item = cJSON_GetObjectItem(channel, "name");
                    cJSON *gpio_item = cJSON_GetObjectItem(channel, "gpio");
                    cJSON *fail_safe_item = cJSON_GetObjectItem(channel, "fail_safe_mode");
                    cJSON *safe_limits = cJSON_GetObjectItem(channel, "safe_limits");
                    
                    if (name_item != NULL && cJSON_IsString(name_item) &&
                        gpio_item != NULL && cJSON_IsNumber(gpio_item)) {
                        pump_channel_config_t *pump_cfg = &pump_configs[pump_count];
                        pump_cfg->channel_name = name_item->valuestring;
                        pump_cfg->gpio_pin = (int)cJSON_GetNumberValue(gpio_item);
                        pump_cfg->use_relay = false; // По умолчанию прямое управление через GPIO
                        pump_cfg->relay_channel = NULL;
                        pump_cfg->ml_per_second = 2.0f; // Значение по умолчанию
                        
                        // Определяем fail_safe_mode
                        if (fail_safe_item != NULL && cJSON_IsString(fail_safe_item)) {
                            pump_cfg->fail_safe_nc = (strcmp(fail_safe_item->valuestring, "NC") == 0);
                        } else {
                            pump_cfg->fail_safe_nc = false; // По умолчанию NO
                        }
                        
                        // Извлекаем safe_limits
                        if (safe_limits != NULL && cJSON_IsObject(safe_limits)) {
                            cJSON *max_duration = cJSON_GetObjectItem(safe_limits, "max_duration_ms");
                            cJSON *min_off = cJSON_GetObjectItem(safe_limits, "min_off_ms");
                            
                            if (max_duration != NULL && cJSON_IsNumber(max_duration)) {
                                pump_cfg->max_duration_ms = (uint32_t)cJSON_GetNumberValue(max_duration);
                            } else {
                                pump_cfg->max_duration_ms = 60000; // 60 секунд по умолчанию
                            }
                            
                            if (min_off != NULL && cJSON_IsNumber(min_off)) {
                                pump_cfg->min_off_time_ms = (uint32_t)cJSON_GetNumberValue(min_off);
                            } else {
                                pump_cfg->min_off_time_ms = 5000; // 5 секунд по умолчанию
                            }
                        } else {
                            pump_cfg->max_duration_ms = 60000;
                            pump_cfg->min_off_time_ms = 5000;
                        }
                        
                        pump_count++;
                    }
                }
            }
        }
    }
    
    if (pump_count == 0) {
        cJSON_Delete(config);
        ESP_LOGW(TAG, "No pump channels found in config");
        return ESP_ERR_NOT_FOUND;
    }
    
    // Инициализация насосов
    esp_err_t init_err = pump_driver_init(pump_configs, pump_count);
    if (init_err != ESP_OK) {
        cJSON_Delete(config);
        return init_err;
    }
    
    // Попытка инициализации INA209 из конфигурации
    cJSON *limits = cJSON_GetObjectItem(config, "limits");
    if (limits != NULL && cJSON_IsObject(limits)) {
        cJSON *currentMin = cJSON_GetObjectItem(limits, "currentMin");
        cJSON *currentMax = cJSON_GetObjectItem(limits, "currentMax");
        
        if (currentMin != NULL && currentMax != NULL && 
            cJSON_IsNumber(currentMin) && cJSON_IsNumber(currentMax)) {
            ina209_config_t ina209_cfg = {0};
            ina209_cfg.i2c_address = 0x40; // Значение по умолчанию
            ina209_cfg.shunt_resistance_ohm = 0.01f; // 10 мОм по умолчанию
            ina209_cfg.min_bus_current_on = (float)cJSON_GetNumberValue(currentMin);
            ina209_cfg.max_bus_current_on = (float)cJSON_GetNumberValue(currentMax);
            ina209_cfg.max_current_ma = ina209_cfg.max_bus_current_on * 1.2f; // 20% запас
            
            // Попытка найти INA209 в каналах для получения poll_interval
            cJSON *channels = cJSON_GetObjectItem(config, "channels");
            if (channels != NULL && cJSON_IsArray(channels)) {
                int channel_count = cJSON_GetArraySize(channels);
                for (int i = 0; i < channel_count; i++) {
                    cJSON *ch = cJSON_GetArrayItem(channels, i);
                    if (ch != NULL && cJSON_IsObject(ch)) {
                        cJSON *name = cJSON_GetObjectItem(ch, "name");
                        if (name != NULL && cJSON_IsString(name) && 
                            strcmp(name->valuestring, "pump_bus_current") == 0) {
                            cJSON *poll_interval = cJSON_GetObjectItem(ch, "poll_interval_ms");
                            if (poll_interval != NULL && cJSON_IsNumber(poll_interval)) {
                                // poll_interval можно использовать для периодического опроса
                            }
                        }
                    }
                }
            }
            
            err = pump_driver_set_ina209_config(&ina209_cfg);
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "INA209 initialized from config");
            } else {
                ESP_LOGW(TAG, "INA209 initialization failed, continuing without current monitoring");
            }
        }
    }
    
    cJSON_Delete(config);
    return ESP_OK;
}

esp_err_t pump_driver_deinit(void) {
    if (!s_initialized) {
        return ESP_OK;
    }
    
    // Остановка всех насосов
    pump_driver_emergency_stop();
    
    // Удаление таймеров
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && s_channels[i].timer != NULL) {
            xTimerDelete(s_channels[i].timer, portMAX_DELAY);
            s_channels[i].timer = NULL;
        }
    }
    
    if (s_mutex != NULL) {
        vSemaphoreDelete(s_mutex);
        s_mutex = NULL;
    }
    
    memset(s_channels, 0, sizeof(s_channels));
    s_channel_count = 0;
    s_initialized = false;
    
    ESP_LOGI(TAG, "Pump driver deinitialized");
    return ESP_OK;
}

static pump_channel_t *find_channel(const char *channel_name) {
    if (channel_name == NULL) {
        return NULL;
    }
    
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && 
            strcmp(s_channels[i].channel_name, channel_name) == 0) {
            return &s_channels[i];
        }
    }
    
    return NULL;
}

esp_err_t pump_driver_run(const char *channel_name, uint32_t duration_ms) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Pump driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (channel_name == NULL || duration_ms == 0) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex");
        return ESP_ERR_TIMEOUT;
    }
    
    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Channel not found: %s", channel_name);
        return ESP_ERR_NOT_FOUND;
    }
    
    // Проверка cooldown
    if (channel->current_state == PUMP_STATE_COOLDOWN) {
        uint64_t now_ms = esp_timer_get_time() / 1000;
        if (now_ms < channel->last_stop_time_ms + channel->min_off_time_ms) {
            uint32_t remaining_ms = (channel->last_stop_time_ms + channel->min_off_time_ms) - now_ms;
            xSemaphoreGive(s_mutex);
            ESP_LOGW(TAG, "Pump %s in cooldown, %lu ms remaining", channel_name, (unsigned long)remaining_ms);
            return ESP_ERR_INVALID_STATE;
        }
    }
    
    // Проверка, не работает ли уже насос
    if (channel->is_running) {
        xSemaphoreGive(s_mutex);
        ESP_LOGW(TAG, "Pump %s already running", channel_name);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Ограничение максимальной длительности
    if (duration_ms > channel->max_duration_ms) {
        ESP_LOGW(TAG, "Duration %lu ms exceeds max %lu ms, limiting", 
                 (unsigned long)duration_ms, (unsigned long)channel->max_duration_ms);
        duration_ms = channel->max_duration_ms;
    }
    
    xSemaphoreGive(s_mutex);
    return pump_start_internal(channel_name, duration_ms);
}

esp_err_t pump_driver_dose(const char *channel_name, float dose_ml) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Pump driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (channel_name == NULL || dose_ml <= 0.0f) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex");
        return ESP_ERR_TIMEOUT;
    }
    
    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Channel not found: %s", channel_name);
        return ESP_ERR_NOT_FOUND;
    }
    
    if (channel->ml_per_second <= 0.0f) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Pump %s not calibrated (ml_per_second = %.2f)", 
                 channel_name, channel->ml_per_second);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Расчёт времени работы по калибровке
    uint32_t duration_ms = (uint32_t)((dose_ml / channel->ml_per_second) * 1000.0f);
    if (duration_ms == 0) {
        duration_ms = 1; // Минимум 1 мс
    }
    
    xSemaphoreGive(s_mutex);
    
    ESP_LOGI(TAG, "Pump %s: dose %.2f ml = %lu ms", 
             channel_name, dose_ml, (unsigned long)duration_ms);
    
    return pump_driver_run(channel_name, duration_ms);
}

esp_err_t pump_driver_stop(const char *channel_name) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Pump driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (channel_name == NULL) {
        ESP_LOGE(TAG, "Invalid channel name");
        return ESP_ERR_INVALID_ARG;
    }
    
    return pump_stop_internal(channel_name);
}

esp_err_t pump_driver_emergency_stop(void) {
    ESP_LOGW(TAG, "EMERGENCY STOP - all pumps");
    
    if (!s_initialized) {
        return ESP_OK;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex");
        return ESP_ERR_TIMEOUT;
    }
    
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && s_channels[i].is_running) {
            pump_stop_internal(s_channels[i].channel_name);
        }
    }
    
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t pump_driver_get_state(const char *channel_name, pump_driver_state_t *state) {
    if (!s_initialized) {
        ESP_LOGE(TAG, "Pump driver not initialized");
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
    
    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Channel not found: %s", channel_name);
        return ESP_ERR_NOT_FOUND;
    }
    
    // Обновление состояния cooldown
    if (channel->current_state == PUMP_STATE_COOLDOWN) {
        uint64_t now_ms = esp_timer_get_time() / 1000;
        if (now_ms >= channel->last_stop_time_ms + channel->min_off_time_ms) {
            channel->current_state = PUMP_STATE_OFF;
        }
    }
    
    *state = channel->current_state;
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

bool pump_driver_is_running(const char *channel_name) {
    if (!s_initialized || channel_name == NULL) {
        return false;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    
    pump_channel_t *channel = find_channel(channel_name);
    bool running = (channel != NULL && channel->is_running);
    
    xSemaphoreGive(s_mutex);
    return running;
}

bool pump_driver_is_initialized(void) {
    return s_initialized;
}

esp_err_t pump_driver_set_ina209_config(const ina209_config_t *config) {
    if (config == NULL) {
        s_ina209_enabled = false;
        s_ina_status.enabled = false;
        s_ina_status.last_read_valid = false;
        s_ina_status.last_read_overcurrent = false;
        s_ina_status.last_read_undercurrent = false;
        s_ina_status.last_current_ma = 0.0f;
        return ESP_OK;
    }
    
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    memcpy(&s_ina209_config, config, sizeof(ina209_config_t));
    s_ina209_enabled = true;
    
    // Инициализация INA209
    esp_err_t err = ina209_init(config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize INA209: %s", esp_err_to_name(err));
        s_ina209_enabled = false;
    } else {
        ESP_LOGI(TAG, "INA209 configured: min=%.2f mA, max=%.2f mA",
                config->min_bus_current_on, config->max_bus_current_on);
        s_ina_status.enabled = true;
        s_ina_status.last_read_valid = false;
        s_ina_status.last_read_overcurrent = false;
        s_ina_status.last_read_undercurrent = false;
        s_ina_status.last_current_ma = 0.0f;
    }
    
    xSemaphoreGive(s_mutex);
    return err;
}

// Внутренние функции

static esp_err_t pump_start_internal(const char *channel_name, uint32_t duration_ms) {
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        return ESP_ERR_NOT_FOUND;
    }

    ESP_LOGI(TAG, "Starting pump %s: %lu ms (GPIO %d)",
             channel_name, (unsigned long)duration_ms, channel->gpio_pin);
    channel->last_command_success = false;
    channel->stats.last_run_success = false;

    // Включение насоса
    esp_err_t err = pump_set_gpio_state(channel, true);
    if (err != ESP_OK) {
        pump_record_failure(channel);
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "Failed to set GPIO state for pump %s", channel_name);
        return err;
    }

    // Если INA209 настроен, ждем стабилизации и проверяем ток
    if (s_ina209_enabled) {
        xSemaphoreGive(s_mutex);
        vTaskDelay(pdMS_TO_TICKS(s_stabilization_delay_ms));
        if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
            return ESP_ERR_TIMEOUT;
        }

        ina209_reading_t reading = {0};
        s_ina_status.enabled = true;
        s_ina_status.last_read_valid = false;
        s_ina_status.last_read_overcurrent = false;
        s_ina_status.last_read_undercurrent = false;
        s_ina_status.last_current_ma = 0.0f;

        err = ina209_read(&reading);
        if (err == ESP_OK && reading.valid) {
            float current_ma = reading.bus_current_ma;
            ESP_LOGI(TAG, "Pump %s started, bus current: %.2f mA", channel_name, current_ma);

            s_ina_status.last_read_valid = true;
            s_ina_status.last_current_ma = current_ma;

            bool in_range = ina209_check_current_range(current_ma);
            bool undercurrent = current_ma < s_ina209_config.min_bus_current_on;
            bool overcurrent = current_ma > s_ina209_config.max_bus_current_on;
            s_ina_status.last_read_undercurrent = undercurrent;
            s_ina_status.last_read_overcurrent = overcurrent;

            if (!in_range) {
                ESP_LOGE(TAG, "Pump %s current out of range: %.2f mA (expected: %.2f-%.2f mA)",
                        channel_name, current_ma,
                        s_ina209_config.min_bus_current_on, s_ina209_config.max_bus_current_on);

                pump_record_overcurrent(channel, undercurrent);
                xSemaphoreGive(s_mutex);
                pump_stop_internal(channel_name);

                if (undercurrent) {
                    return ESP_ERR_INVALID_RESPONSE;
                }
                return ESP_ERR_INVALID_SIZE;
            }
        } else {
            ESP_LOGW(TAG, "Failed to read INA209 for pump %s: %s", channel_name, esp_err_to_name(err));
            s_ina_status.last_read_valid = false;
        }
    } else {
        s_ina_status.enabled = false;
    }

    // Обновление состояния
    channel->current_state = PUMP_STATE_ON;
    channel->is_running = true;
    channel->start_time_ms = esp_timer_get_time() / 1000; // мс
    channel->stats.last_start_timestamp_ms = channel->start_time_ms;
    channel->run_duration_ms = duration_ms;
    channel->stats.last_run_success = true;
    channel->stats.run_count++;
    channel->last_command_success = true;

    // Запуск таймера автоостановки
    xTimerChangePeriod(channel->timer, pdMS_TO_TICKS(duration_ms), 0);
    xTimerStart(channel->timer, 0);
    
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

static esp_err_t pump_stop_internal(const char *channel_name) {
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        return ESP_ERR_NOT_FOUND;
    }
    
    if (!channel->is_running) {
        xSemaphoreGive(s_mutex);
        return ESP_OK; // Уже остановлен
    }
    
    // Выключение насоса
    pump_set_gpio_state(channel, false);
    
    // Остановка таймера
    xTimerStop(channel->timer, 0);
    
    // Обновление статистики
    uint64_t current_time_ms = esp_timer_get_time() / 1000;
    uint64_t actual_time_ms = current_time_ms - channel->start_time_ms;
    
    channel->last_stop_time_ms = current_time_ms;
    channel->is_running = false;
    channel->current_state = PUMP_STATE_COOLDOWN;
    channel->stats.total_run_time_ms += actual_time_ms;
    channel->stats.last_run_duration_ms = (uint32_t)actual_time_ms;
    channel->stats.last_stop_timestamp_ms = current_time_ms;
    channel->stats.last_run_success = channel->last_command_success;

    ESP_LOGI(TAG, "Pump %s stopped: %llu ms (GPIO %d)",
             channel_name, (unsigned long long)actual_time_ms, channel->gpio_pin);
    
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

static void pump_timer_callback(TimerHandle_t timer) {
    size_t channel_index = (size_t)(uintptr_t)pvTimerGetTimerID(timer);

    if (channel_index < s_channel_count && s_channels[channel_index].initialized) {
        ESP_LOGD(TAG, "Timer callback for pump %s", s_channels[channel_index].channel_name);
        pump_stop_internal(s_channels[channel_index].channel_name);
    }
}

static void pump_record_failure(pump_channel_t *channel) {
    if (channel == NULL) {
        return;
    }

    channel->stats.failure_count++;
    channel->last_command_success = false;
    channel->stats.last_run_success = false;
}

static void pump_record_overcurrent(pump_channel_t *channel, bool undercurrent) {
    if (channel == NULL) {
        return;
    }

    if (undercurrent) {
        channel->stats.no_current_events++;
    } else {
        channel->stats.overcurrent_events++;
    }

    pump_record_failure(channel);
}

static void pump_fill_channel_health(const pump_channel_t *channel, pump_driver_channel_health_t *out) {
    if (channel == NULL || out == NULL) {
        return;
    }

    memset(out, 0, sizeof(*out));
    strncpy(out->channel_name, channel->channel_name, sizeof(out->channel_name) - 1);
    out->last_run_duration_ms = channel->stats.last_run_duration_ms;
    out->total_run_time_ms = channel->stats.total_run_time_ms;
    out->run_count = channel->stats.run_count;
    out->failure_count = channel->stats.failure_count;
    out->overcurrent_events = channel->stats.overcurrent_events;
    out->no_current_events = channel->stats.no_current_events;
    out->last_start_timestamp_ms = channel->stats.last_start_timestamp_ms;
    out->last_stop_timestamp_ms = channel->stats.last_stop_timestamp_ms;
    out->last_run_success = channel->stats.last_run_success;
    out->is_running = channel->is_running;
}

esp_err_t pump_driver_get_health_snapshot(pump_driver_health_snapshot_t *snapshot) {
    if (snapshot == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    memset(snapshot, 0, sizeof(*snapshot));

    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    size_t out_index = 0;
    for (size_t i = 0; i < s_channel_count && out_index < PUMP_DRIVER_MAX_CHANNELS; i++) {
        if (!s_channels[i].initialized) {
            continue;
        }

        pump_fill_channel_health(&s_channels[i], &snapshot->channels[out_index]);
        out_index++;
    }

    snapshot->channel_count = out_index;
    snapshot->ina_status = s_ina_status;
    snapshot->ina_status.enabled = s_ina209_enabled && snapshot->ina_status.enabled;

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t pump_driver_get_channel_health(const char *channel_name, pump_driver_channel_health_t *stats) {
    if (channel_name == NULL || stats == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    pump_channel_t *channel = find_channel(channel_name);
    if (channel == NULL || !channel->initialized) {
        xSemaphoreGive(s_mutex);
        return ESP_ERR_NOT_FOUND;
    }

    pump_fill_channel_health(channel, stats);

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

