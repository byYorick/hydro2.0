/**
 * @file pump_node_framework_integration.c
 * @brief Интеграция pump_node с node_framework
 * 
 * Этот файл связывает pump_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "pump_node_framework_integration.h"
#include "pump_node_defaults.h"
#include "pump_node_init.h"
#include "node_framework.h"
#include "node_state_manager.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "pump_driver.h"
#include "ina209.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include <string.h>

static const char *TAG = "pump_node_framework";

// Forward declaration для callback safe_mode
static esp_err_t pump_node_disable_actuators_in_safe_mode(void *user_ctx);

#define PUMP_NODE_CMD_QUEUE_MAX 8
#define PUMP_NODE_DONE_QUEUE_MAX 8
#define PUMP_NODE_CMD_ID_LEN 64

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[PUMP_NODE_CMD_ID_LEN];
    uint32_t duration_ms;
} pump_node_cmd_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[PUMP_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
    TimerHandle_t timer;
} pump_node_done_entry_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[PUMP_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
} pump_node_done_event_t;

static pump_node_cmd_t s_cmd_queue[PUMP_NODE_CMD_QUEUE_MAX] = {0};
static size_t s_cmd_queue_head = 0;
static size_t s_cmd_queue_tail = 0;
static size_t s_cmd_queue_count = 0;
static SemaphoreHandle_t s_cmd_queue_mutex = NULL;
static QueueHandle_t s_cmd_work_queue = NULL;
static TimerHandle_t s_cmd_retry_timer = NULL;

static pump_node_done_entry_t s_done_entries[PUMP_NODE_DONE_QUEUE_MAX] = {0};
static QueueHandle_t s_done_queue = NULL;

static void pump_node_cmd_queue_task(void *pvParameters);
static void pump_node_done_task(void *pvParameters);
static void pump_node_process_cmd_queue(void);
static void pump_node_signal_cmd_process(void);
static void pump_node_retry_timer_cb(TimerHandle_t timer);
static void pump_node_done_timer_cb(TimerHandle_t timer);
static bool pump_node_cmd_queue_push(const pump_node_cmd_t *cmd);
static bool pump_node_cmd_queue_pop(pump_node_cmd_t *cmd);
static bool pump_node_any_pump_running(void);
static pump_node_done_entry_t *pump_node_get_done_entry(const char *channel, bool create);

/**
 * @brief Callback для инициализации каналов при применении конфигурации
 */
static esp_err_t pump_node_init_channel_callback(const char *channel_name, const cJSON *channel_config, void *user_ctx) {
    (void)user_ctx;
    
    if (channel_config == NULL || channel_name == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Инициализация насосов обрабатывается через config_apply_channels_pump
    // Этот callback вызывается для каждого канала, но насосы инициализируются централизованно
    ESP_LOGD(TAG, "Channel init callback for: %s", channel_name);
    
    return ESP_OK;
}

/**
 * @brief Обработчик команды run_pump с командным автоматом
 * 
 * Состояния: ACCEPTED -> DONE/FAILED
 */
static esp_err_t handle_run_pump(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    
    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Извлекаем cmd_id из params (он будет добавлен позже в node_command_handler_process)
    // Но для промежуточного ответа нам нужен cmd_id, поэтому получаем его из params
    const char *cmd_id = node_command_handler_get_cmd_id(params);
    
    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    if (!cJSON_IsNumber(duration_item)) {
        *response = node_command_handler_create_response(cmd_id, "FAILED", "missing_duration", "duration_ms is required", NULL);
        return ESP_ERR_INVALID_ARG;
    }
    
    int duration_ms = (int)cJSON_GetNumberValue(duration_item);
    ESP_LOGI(TAG, "Running pump on channel %s for %d ms", channel, duration_ms);
    
    pump_node_cmd_t queued_cmd = {0};
    strncpy(queued_cmd.channel_name, channel, sizeof(queued_cmd.channel_name) - 1);
    if (cmd_id) {
        strncpy(queued_cmd.cmd_id, cmd_id, sizeof(queued_cmd.cmd_id) - 1);
    }
    queued_cmd.duration_ms = (uint32_t)duration_ms;

    if (!pump_node_cmd_queue_push(&queued_cmd)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "FAILED",
            "pump_queue_full",
            "Pump queue is full",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    bool queued = pump_node_any_pump_running();
    uint32_t cooldown_remaining_ms = 0;
    bool cooldown_active = (pump_driver_get_cooldown_remaining(channel, &cooldown_remaining_ms) == ESP_OK &&
                            cooldown_remaining_ms > 0);
    if (cooldown_active) {
        queued = true;
    }

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddNumberToObject(extra, "duration_ms", duration_ms);
        cJSON_AddBoolToObject(extra, "queued", queued);
        if (cooldown_active) {
            cJSON_AddNumberToObject(extra, "cooldown_ms", cooldown_remaining_ms);
        }
    }
    *response = node_command_handler_create_response(
        cmd_id,
        "ACCEPTED",
        NULL,
        NULL,
        extra
    );
    if (extra) {
        cJSON_Delete(extra);
    }

    if (cooldown_active) {
        pump_node_signal_cmd_process();
    } else {
        pump_node_signal_cmd_process();
    }
    return ESP_OK;
}

/**
 * @brief Callback для публикации телеметрии pump
 */
esp_err_t pump_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;
    
    // Убрана проверка mqtt_manager_is_connected - батч телеметрии работает даже при оффлайне
    // Данные будут сохранены в батч и отправлены после восстановления связи
    
    // Чтение тока из INA209
    ina209_reading_t reading;
    esp_err_t err = ina209_read(&reading);
    
    if (err == ESP_OK && reading.valid) {
        // Публикация телеметрии тока насоса
        // Используем батч телеметрии, который работает даже при оффлайне
        // unit передается корректно, raw поддерживает отрицательные значения
        // stable=true, так как reading.valid=true означает валидное значение
        node_telemetry_publish_sensor("pump_bus_current", METRIC_TYPE_CURRENT, 
                                      reading.bus_current_ma, "mA", 
                                      (int32_t)reading.bus_current_ma, false, true);
        
        // Дополнительные поля можно добавить через расширенный API, если нужно
        // Пока публикуем только основное значение
    } else {
        ESP_LOGW(TAG, "Failed to read INA209: %s", esp_err_to_name(err));
        // Не возвращаем ошибку - продолжаем работу даже при ошибке чтения INA209
        // Это позволяет не терять другие данные телеметрии
    }
    
    return ESP_OK;
}

/**
 * @brief Wrapper для обработки config сообщений через node_framework
 */
static void pump_node_config_handler_wrapper(const char *topic, const char *data, int data_len, void *user_ctx) {
    node_config_handler_process(topic, data, data_len, user_ctx);
}

/**
 * @brief Wrapper для обработки command сообщений через node_framework
 */
static void pump_node_command_handler_wrapper(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

static bool pump_node_any_pump_running(void) {
    pump_driver_health_snapshot_t snapshot = {0};
    if (pump_driver_get_health_snapshot(&snapshot) != ESP_OK) {
        return false;
    }
    for (size_t i = 0; i < snapshot.channel_count; i++) {
        if (snapshot.channels[i].is_running) {
            return true;
        }
    }
    return false;
}

static bool pump_node_cmd_queue_push(const pump_node_cmd_t *cmd) {
    if (!cmd || !s_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(s_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (s_cmd_queue_count >= PUMP_NODE_CMD_QUEUE_MAX) {
        xSemaphoreGive(s_cmd_queue_mutex);
        return false;
    }
    s_cmd_queue[s_cmd_queue_tail] = *cmd;
    s_cmd_queue_tail = (s_cmd_queue_tail + 1) % PUMP_NODE_CMD_QUEUE_MAX;
    s_cmd_queue_count++;
    xSemaphoreGive(s_cmd_queue_mutex);
    return true;
}

static bool pump_node_cmd_queue_pop(pump_node_cmd_t *cmd) {
    if (!cmd || !s_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(s_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (s_cmd_queue_count == 0) {
        xSemaphoreGive(s_cmd_queue_mutex);
        return false;
    }
    *cmd = s_cmd_queue[s_cmd_queue_head];
    memset(&s_cmd_queue[s_cmd_queue_head], 0, sizeof(s_cmd_queue[s_cmd_queue_head]));
    s_cmd_queue_head = (s_cmd_queue_head + 1) % PUMP_NODE_CMD_QUEUE_MAX;
    s_cmd_queue_count--;
    xSemaphoreGive(s_cmd_queue_mutex);
    return true;
}

static void pump_node_signal_cmd_process(void) {
    if (!s_cmd_work_queue) {
        return;
    }
    uint8_t token = 1;
    xQueueSend(s_cmd_work_queue, &token, 0);
}

static pump_node_done_entry_t *pump_node_get_done_entry(const char *channel, bool create) {
    if (!channel) {
        return NULL;
    }
    for (size_t i = 0; i < PUMP_NODE_DONE_QUEUE_MAX; i++) {
        if (s_done_entries[i].channel_name[0] != '\0' &&
            strncmp(s_done_entries[i].channel_name, channel, sizeof(s_done_entries[i].channel_name)) == 0) {
            return &s_done_entries[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (size_t i = 0; i < PUMP_NODE_DONE_QUEUE_MAX; i++) {
        if (s_done_entries[i].channel_name[0] == '\0') {
            strncpy(s_done_entries[i].channel_name, channel, sizeof(s_done_entries[i].channel_name) - 1);
            s_done_entries[i].timer = xTimerCreate(
                "pump_done",
                pdMS_TO_TICKS(1000),
                pdFALSE,
                &s_done_entries[i],
                pump_node_done_timer_cb
            );
            if (!s_done_entries[i].timer) {
                s_done_entries[i].channel_name[0] = '\0';
                return NULL;
            }
            return &s_done_entries[i];
        }
    }
    return NULL;
}

static void pump_node_schedule_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
                                    float current_ma, bool current_valid) {
    pump_node_done_entry_t *entry = pump_node_get_done_entry(channel, true);
    if (!entry) {
        ESP_LOGW(TAG, "No done entry available for channel %s", channel);
        return;
    }
    if (cmd_id) {
        strncpy(entry->cmd_id, cmd_id, sizeof(entry->cmd_id) - 1);
    } else {
        entry->cmd_id[0] = '\0';
    }
    entry->current_ma = current_ma;
    entry->current_valid = current_valid;
    if (duration_ms == 0) {
        duration_ms = 1;
    }
    if (xTimerChangePeriod(entry->timer, pdMS_TO_TICKS(duration_ms), 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to arm done timer for %s", channel);
        return;
    }
    xTimerStart(entry->timer, 0);
}

static void pump_node_done_timer_cb(TimerHandle_t timer) {
    pump_node_done_entry_t *entry = (pump_node_done_entry_t *)pvTimerGetTimerID(timer);
    if (!entry || entry->cmd_id[0] == '\0' || !s_done_queue) {
        return;
    }
    pump_node_done_event_t event = {0};
    strncpy(event.channel_name, entry->channel_name, sizeof(event.channel_name) - 1);
    strncpy(event.cmd_id, entry->cmd_id, sizeof(event.cmd_id) - 1);
    event.current_ma = entry->current_ma;
    event.current_valid = entry->current_valid;
    if (xQueueSend(s_done_queue, &event, 0) != pdTRUE) {
        ESP_LOGW(TAG, "Done queue full for channel %s", entry->channel_name);
    }
}

static void pump_node_done_task(void *pvParameters) {
    (void)pvParameters;
    pump_node_done_event_t event = {0};
    while (true) {
        if (xQueueReceive(s_done_queue, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "current_ma", event.current_ma);
            cJSON_AddBoolToObject(extra, "current_valid", event.current_valid);
        }
        cJSON *response = node_command_handler_create_response(
            event.cmd_id[0] ? event.cmd_id : NULL,
            "DONE",
            NULL,
            NULL,
            extra
        );
        if (extra) {
            cJSON_Delete(extra);
        }
        if (response) {
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(event.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        if (event.cmd_id[0]) {
            node_command_handler_cache_final_status(event.cmd_id, event.channel_name, "DONE");
        }
        pump_node_signal_cmd_process();
    }
}

static void pump_node_retry_timer_cb(TimerHandle_t timer) {
    (void)timer;
    pump_node_signal_cmd_process();
}

static void pump_node_process_cmd_queue(void) {
    if (pump_node_any_pump_running()) {
        return;
    }

    pump_node_cmd_t cmd = {0};
    if (!pump_node_cmd_queue_pop(&cmd)) {
        return;
    }

    uint32_t cooldown_ms = 0;
    if (pump_driver_get_cooldown_remaining(cmd.channel_name, &cooldown_ms) == ESP_OK && cooldown_ms > 0) {
        if (!pump_node_cmd_queue_push(&cmd)) {
            cJSON *response = node_command_handler_create_response(
                cmd.cmd_id[0] ? cmd.cmd_id : NULL,
                "FAILED",
                "pump_queue_full",
                "Pump queue is full",
                NULL
            );
            if (response) {
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
            if (cmd.cmd_id[0]) {
                node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "FAILED");
            }
        }
        if (s_cmd_retry_timer && cooldown_ms > 0) {
            xTimerChangePeriod(s_cmd_retry_timer, pdMS_TO_TICKS(cooldown_ms), 0);
            xTimerStart(s_cmd_retry_timer, 0);
        }
        return;
    }

    esp_err_t err = pump_driver_run(cmd.channel_name, cmd.duration_ms);
    if (err != ESP_OK) {
        const char *error_code = "pump_driver_failed";
        const char *error_message = esp_err_to_name(err);
        if (err == ESP_ERR_INVALID_RESPONSE) {
            error_code = "current_not_detected";
            error_message = "Pump started but no current detected";
        } else if (err == ESP_ERR_INVALID_SIZE) {
            error_code = "overcurrent";
            error_message = "Pump current exceeds safe limit";
        }
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "pump_driver", err, error_message);
        cJSON *response = node_command_handler_create_response(
            cmd.cmd_id[0] ? cmd.cmd_id : NULL,
            "FAILED",
            error_code,
            error_message,
            NULL
        );
        if (response) {
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        if (cmd.cmd_id[0]) {
            node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "FAILED");
        }
        pump_node_signal_cmd_process();
        return;
    }

    ina209_reading_t reading = {0};
    bool current_valid = (ina209_read(&reading) == ESP_OK && reading.valid);
    float current_ma = current_valid ? reading.bus_current_ma : 0.0f;
    pump_node_schedule_done(cmd.channel_name, cmd.cmd_id, cmd.duration_ms, current_ma, current_valid);
}

static void pump_node_cmd_queue_task(void *pvParameters) {
    (void)pvParameters;
    uint8_t token = 0;
    while (true) {
        if (xQueueReceive(s_cmd_work_queue, &token, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        pump_node_process_cmd_queue();
    }
}


/**
 * @brief Инициализация интеграции pump_node с node_framework
 */
esp_err_t pump_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing pump_node framework integration...");
    
    // Конфигурация node_framework
    node_framework_config_t config = {
        .node_type = "pump",
        .default_node_id = PUMP_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = PUMP_NODE_DEFAULT_GH_UID,
        .default_zone_uid = PUMP_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = pump_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = pump_node_publish_telemetry_callback,
        .user_ctx = NULL
    };
    
    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", err, "Node framework initialization failed");
        return err;
    }

    if (!s_cmd_queue_mutex) {
        s_cmd_queue_mutex = xSemaphoreCreateMutex();
        if (!s_cmd_queue_mutex) {
            ESP_LOGE(TAG, "Failed to create pump command queue mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    if (!s_cmd_work_queue) {
        s_cmd_work_queue = xQueueCreate(PUMP_NODE_CMD_QUEUE_MAX, sizeof(uint8_t));
        if (!s_cmd_work_queue) {
            ESP_LOGE(TAG, "Failed to create pump command queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(pump_node_cmd_queue_task, "pump_cmd_queue", 4096, NULL, 4, NULL);
    }
    if (!s_done_queue) {
        s_done_queue = xQueueCreate(PUMP_NODE_DONE_QUEUE_MAX, sizeof(pump_node_done_event_t));
        if (!s_done_queue) {
            ESP_LOGE(TAG, "Failed to create pump done queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(pump_node_done_task, "pump_done", 4096, NULL, 4, NULL);
    }
    if (!s_cmd_retry_timer) {
        s_cmd_retry_timer = xTimerCreate("pump_retry", pdMS_TO_TICKS(1000), pdFALSE, NULL, pump_node_retry_timer_cb);
        if (!s_cmd_retry_timer) {
            ESP_LOGW(TAG, "Failed to create pump retry timer");
        }
    }
    
    // Регистрация обработчиков команд
    err = node_command_handler_register("run_pump", handle_run_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(pump_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }
    
    ESP_LOGI(TAG, "pump_node framework integration initialized");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t pump_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    return pump_driver_emergency_stop();
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void pump_node_framework_register_mqtt_handlers(void) {
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(pump_node_config_handler_wrapper, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(pump_node_command_handler_wrapper, NULL);
    
    // Регистрация MQTT callbacks в node_config_handler для config_apply_mqtt
    // Это позволяет автоматически переподключать MQTT при изменении конфига
    node_config_handler_set_mqtt_callbacks(
        pump_node_config_handler_wrapper,
        pump_node_command_handler_wrapper,
        pump_node_mqtt_connection_cb,  // connection_cb
        NULL,
        PUMP_NODE_DEFAULT_NODE_ID,
        PUMP_NODE_DEFAULT_GH_UID,
        PUMP_NODE_DEFAULT_ZONE_UID
    );
    
    ESP_LOGI(TAG, "MQTT handlers registered via node_framework");
}
