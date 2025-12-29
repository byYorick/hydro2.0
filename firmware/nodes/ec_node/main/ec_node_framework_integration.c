/**
 * @file ec_node_framework_integration.c
 * @brief Интеграция ec_node с node_framework
 * 
 * Этот файл связывает ec_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "ec_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "ec_node_defaults.h"
#include "ec_node_channel_map.h"
#include "pump_driver.h"
#include "trema_ec.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <math.h>
#include <float.h>

static const char *TAG = "ec_node_fw";

// Параметры для отложенного ответа DONE после теста насоса
#define EC_NODE_MAX_TEST_CHANNELS 8
#define EC_NODE_MAX_CHANNEL_NAME_LEN 64
#define EC_NODE_MAX_CMD_ID_LEN 64
#define EC_NODE_PUMP_QUEUE_MAX 8

typedef struct {
    char channel_name[EC_NODE_MAX_CHANNEL_NAME_LEN];
    char cmd_id[EC_NODE_MAX_CMD_ID_LEN];
    TimerHandle_t timer;
    bool in_use;
    float current_ma;
    bool current_valid;
} ec_node_test_entry_t;

typedef struct {
    char channel_name[EC_NODE_MAX_CHANNEL_NAME_LEN];
    char cmd_id[EC_NODE_MAX_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
} ec_node_test_done_event_t;

typedef struct {
    char channel_name[EC_NODE_MAX_CHANNEL_NAME_LEN];
    char cmd_id[EC_NODE_MAX_CMD_ID_LEN];
    uint32_t duration_ms;
} ec_node_pump_cmd_t;

static ec_node_test_entry_t s_test_entries[EC_NODE_MAX_TEST_CHANNELS] = {0};
static QueueHandle_t s_test_done_queue = NULL;
static QueueHandle_t s_pump_work_queue = NULL;
static SemaphoreHandle_t s_pump_queue_mutex = NULL;
static ec_node_pump_cmd_t s_pump_queue[EC_NODE_PUMP_QUEUE_MAX] = {0};
static size_t s_pump_queue_head = 0;
static size_t s_pump_queue_tail = 0;
static size_t s_pump_queue_count = 0;
static TimerHandle_t s_pump_retry_timer = NULL;

// Forward declaration для callback safe_mode
static esp_err_t ec_node_disable_actuators_in_safe_mode(void *user_ctx);

static cJSON *ec_node_channels_callback(void *user_ctx);
static void ec_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
);
static void ec_node_test_done_task(void *pvParameters);
static void ec_node_pump_queue_task(void *pvParameters);
static void ec_node_test_done_timer_cb(TimerHandle_t timer);
static ec_node_test_entry_t *ec_node_get_test_entry(const char *channel, bool create);
static void ec_node_schedule_test_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
                                       float current_ma, bool current_valid);
static void ec_node_cancel_test_done(const char *channel, bool clear_cmd_id);
static void ec_node_get_last_pump_current(float *current_ma, bool *current_valid);
static bool ec_node_any_pump_running(void);
static bool ec_node_is_channel_in_cooldown(const char *channel, uint32_t *remaining_ms);
static bool ec_node_pump_queue_push(const ec_node_pump_cmd_t *cmd);
static bool ec_node_pump_queue_pop(ec_node_pump_cmd_t *cmd);
static size_t ec_node_pump_queue_count(void);
static size_t ec_node_pump_queue_remove_channel(const char *channel);
static void ec_node_process_pump_queue(void);
static void ec_node_schedule_pump_retry(uint32_t delay_ms);
static void ec_node_pump_retry_timer_cb(TimerHandle_t timer);
static void ec_node_signal_pump_queue_process(void);
static esp_err_t ec_node_start_pump_command(const char *channel, uint32_t duration_ms,
                                            float *current_ma, bool *current_valid);
static cJSON *ec_node_create_pump_failed_response(const char *cmd_id, const char *channel, esp_err_t err);

// Callback для инициализации каналов из NodeConfig
static esp_err_t ec_node_init_channel_callback(
    const char *channel_name,
    const cJSON *channel_config,
    void *user_ctx
) {
    (void)user_ctx;
    
    if (channel_name == NULL || channel_config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Initializing channel: %s", channel_name);

    // Проверяем тип канала
    cJSON *type_item = cJSON_GetObjectItem(channel_config, "type");
    if (!cJSON_IsString(type_item)) {
        ESP_LOGW(TAG, "Channel %s: missing or invalid type", channel_name);
        return ESP_ERR_INVALID_ARG;
    }

    const char *channel_type = type_item->valuestring;
    const char *actuator_type = channel_type;

    if (strcasecmp(channel_type, "ACTUATOR") == 0) {
        cJSON *actuator_item = cJSON_GetObjectItem(channel_config, "actuator_type");
        if (!cJSON_IsString(actuator_item)) {
            ESP_LOGW(TAG, "Channel %s: missing or invalid actuator_type", channel_name);
            return ESP_ERR_INVALID_ARG;
        }
        actuator_type = actuator_item->valuestring;
    }

    // Инициализация насосов
    // Примечание: pump_driver инициализируется через pump_driver_init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcasecmp(actuator_type, "PUMP") == 0 || strcasecmp(actuator_type, "PERISTALTIC_PUMP") == 0) {
        cJSON *pin_item = cJSON_GetObjectItem(channel_config, "pin");
        cJSON *gpio_item = cJSON_GetObjectItem(channel_config, "gpio");
        cJSON *pin_src = cJSON_IsNumber(pin_item) ? pin_item : (cJSON_IsNumber(gpio_item) ? gpio_item : NULL);
        if (pin_src) {
            int pin = pin_src->valueint;
            ESP_LOGI(TAG, "Pump channel %s configured on pin %d (will be initialized via pump_driver_init_from_config)",
                    channel_name, pin);
        } else {
            ESP_LOGI(TAG, "Pump channel %s configured (GPIO resolved in firmware)", channel_name);
        }
        return ESP_OK;
    }

    return ESP_OK;
}

// Обработчик команды run_pump
static esp_err_t handle_run_pump(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *cmd_id = node_command_handler_get_cmd_id(params);
    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    if (!cJSON_IsNumber(duration_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_params",
            "Missing or invalid duration_ms",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    int duration_ms = duration_item->valueint;
    if (duration_ms <= 0 || duration_ms > 60000) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_params",
            "duration_ms must be between 1 and 60000",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t cooldown_remaining_ms = 0;
    bool channel_in_cooldown = ec_node_is_channel_in_cooldown(channel, &cooldown_remaining_ms);
    bool should_queue = ec_node_any_pump_running() || channel_in_cooldown;

    ec_node_pump_cmd_t queued_cmd = {0};
    strncpy(queued_cmd.channel_name, channel, sizeof(queued_cmd.channel_name) - 1);
    if (cmd_id) {
        strncpy(queued_cmd.cmd_id, cmd_id, sizeof(queued_cmd.cmd_id) - 1);
    }
    queued_cmd.duration_ms = (uint32_t)duration_ms;

    if (!ec_node_pump_queue_push(&queued_cmd)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "FAILED",
            "pump_queue_full",
            "Pump queue is full",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddNumberToObject(extra, "duration_ms", duration_ms);
        cJSON_AddBoolToObject(extra, "queued", should_queue);
        if (channel_in_cooldown && cooldown_remaining_ms > 0) {
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

    ESP_LOGI(TAG, "Pump %s accepted for %d ms%s", channel, duration_ms,
             should_queue ? " (queued)" : "");
    if (channel_in_cooldown && cooldown_remaining_ms > 0) {
        ec_node_schedule_pump_retry(cooldown_remaining_ms);
    }
    ec_node_signal_pump_queue_process();
    return ESP_OK;
}

// Обработчик команды stop_pump
static esp_err_t handle_stop_pump(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)params;
    (void)user_ctx;

    if (channel == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = pump_driver_stop(channel);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "pump_error",
            "Failed to stop pump",
            NULL
        );
        return err;
    }

    ec_node_cancel_test_done(channel, true);
    ec_node_pump_queue_remove_channel(channel);
    *response = node_command_handler_create_response(
        NULL,
        "DONE",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "Pump %s stopped", channel);
    ec_node_process_pump_queue();
    return ESP_OK;
}

// Обработчик команды calibrate
static esp_err_t handle_calibrate(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)user_ctx;

    if (params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *stage_item = cJSON_GetObjectItem(params, "stage");
    cJSON *tds_value_item = cJSON_GetObjectItem(params, "tds_value");

    if (!cJSON_IsNumber(stage_item) || !cJSON_IsNumber(tds_value_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_format",
            "Missing stage or tds_value",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
    uint16_t known_tds = (uint16_t)cJSON_GetNumberValue(tds_value_item);

    if (stage != 1 && stage != 2) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_stage",
            "Stage must be 1 or 2",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (known_tds > 10000) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_tds",
            "TDS value must be <= 10000",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Starting EC calibration: stage=%d, known_tds=%u ppm", stage, known_tds);

    bool cal_success = trema_ec_calibrate(stage, known_tds);
    trema_ec_error_t cal_error = trema_ec_get_error();

    if (!cal_success || cal_error != TREMA_EC_ERROR_NONE) {
        const char *error_msg = "Calibration failed";
        if (cal_error == TREMA_EC_ERROR_NOT_INITIALIZED) {
            error_msg = "EC sensor not initialized";
        } else if (cal_error == TREMA_EC_ERROR_INVALID_VALUE) {
            error_msg = "Invalid calibration value";
        }

        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "calibration_failed",
            error_msg,
            NULL
        );
        return ESP_FAIL;
    }

    *response = node_command_handler_create_response(
        NULL,
        "DONE",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "EC calibration stage %d completed successfully", stage);
    return ESP_OK;
}

// Обработчик команды test_sensor
static esp_err_t handle_test_sensor(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)params;
    (void)user_ctx;

    if (channel == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (strcmp(channel, "ec_sensor") != 0) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_channel",
            "Unknown sensor channel",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "i2c_not_initialized",
            "I2C bus is not initialized",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    float temp_check = 0.0f;
    bool sensor_ready = trema_ec_get_temperature(&temp_check);
    if (!sensor_ready) {
        if (!trema_ec_init()) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "sensor_init_failed",
                "Failed to initialize EC sensor",
                NULL
            );
            return ESP_FAIL;
        }
        sensor_ready = true;
    }

    float ec_value = NAN;
    bool read_success = trema_ec_read(&ec_value);
    bool using_stub = trema_ec_is_using_stub_values();
    trema_ec_error_t read_error = trema_ec_get_error();

    if (!read_success || isnan(ec_value) || !isfinite(ec_value) || read_error != TREMA_EC_ERROR_NONE) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "read_failed",
            "Failed to read EC sensor",
            NULL
        );
        return ESP_FAIL;
    }

    if (using_stub) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "sensor_stub",
            "EC sensor returned stub values",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    int32_t raw_value = (int32_t)(ec_value * 1000.0f);
    uint16_t tds_value = trema_ec_get_tds();

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddNumberToObject(extra, "value", ec_value);
        cJSON_AddStringToObject(extra, "unit", "mS/cm");
        cJSON_AddStringToObject(extra, "metric_type", "ec");
        cJSON_AddNumberToObject(extra, "raw_value", raw_value);
        cJSON_AddBoolToObject(extra, "stable", true);
        if (tds_value > 0) {
            cJSON_AddNumberToObject(extra, "tds_ppm", tds_value);
        }
    }

    *response = node_command_handler_create_response(
        NULL,
        "DONE",
        NULL,
        NULL,
        extra
    );
    if (extra) {
        cJSON_Delete(extra);
    }

    return ESP_OK;
}

// Публикация телеметрии через node_framework
esp_err_t ec_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    // Инициализация сенсора, если не инициализирован
    // Проверяем через попытку чтения температуры (если сенсор не инициализирован, вернет false)
    float temp_check = 0.0f;
    bool sensor_ready = trema_ec_get_temperature(&temp_check);
    
    // trema_ec использует дефолтную шину (I2C_BUS_0)
    if (!sensor_ready && i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        if (trema_ec_init()) {
            ESP_LOGI(TAG, "Trema EC sensor initialized");
            sensor_ready = true;
        }
    }

    // Получение температуры для компенсации
    float compensation_temp = 25.0f;
    bool stored_temp_valid = (config_storage_get_last_temperature(&compensation_temp) == ESP_OK);
    if (!stored_temp_valid) {
        compensation_temp = 25.0f;
    }

    // Применение температурной компенсации
    if (sensor_ready) {
        if (!trema_ec_set_temperature(compensation_temp)) {
            ESP_LOGW(TAG, "Failed to apply stored temperature %.2fC", compensation_temp);
        }
    }

    // Чтение значения EC
    float ec_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    uint16_t tds_value = 0;
    trema_ec_error_t read_error = TREMA_EC_ERROR_NOT_INITIALIZED;

    if (sensor_ready) {
        read_success = trema_ec_read(&ec_value);
        using_stub = trema_ec_is_using_stub_values();
        read_error = trema_ec_get_error();
        if (!read_success || isnan(ec_value)) {
            ESP_LOGW(TAG, "Failed to read EC value, using stub");
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "ec_sensor", ESP_ERR_INVALID_RESPONSE, "Failed to read EC sensor value");
            ec_value = 1.2f;
            using_stub = true;
        }
        tds_value = trema_ec_get_tds();
    } else {
        ESP_LOGW(TAG, "EC sensor not initialized, using stub value");
        node_state_manager_report_error(ERROR_LEVEL_WARNING, "ec_sensor", ESP_ERR_INVALID_STATE, "EC sensor not initialized");
        ec_value = 1.2f;
        using_stub = true;
    }

    // Публикация EC через node_telemetry_engine
    int32_t raw_value = (int32_t)(ec_value * 1000);  // Raw value в тысячных
    esp_err_t err = node_telemetry_publish_sensor(
        "ec_sensor",
        METRIC_TYPE_EC,
        ec_value,
        "mS/cm",
        raw_value,
        using_stub,
        true  // is_stable - всегда true для EC
    );

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish EC telemetry: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish EC telemetry");
    }

    // Публикация TDS (если доступно) - используем METRIC_TYPE_CUSTOM
    if (sensor_ready && read_error == TREMA_EC_ERROR_NONE && tds_value > 0) {
        err = node_telemetry_publish_sensor(
            "ec_sensor",
            METRIC_TYPE_CUSTOM,
            (float)tds_value,
            "ppm",
            tds_value,
            false,  // not stub
            true     // is_stable
        );

        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish TDS telemetry: %s", esp_err_to_name(err));
        }
    }

    return ESP_OK;
}

// Wrapper для обработчика config (C-совместимый)
static void ec_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    if (data == NULL || data_len <= 0) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (config == NULL) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    cJSON_DeleteItemFromObject(config, "channels");
    cJSON *channels = ec_node_build_config_channels();
    if (channels == NULL) {
        ESP_LOGW(TAG, "Failed to build firmware channels");
        cJSON_Delete(config);
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    cJSON_AddItemToObject(config, "channels", channels);

    cJSON *limits = cJSON_GetObjectItem(config, "limits");
    if (!limits || !cJSON_IsObject(limits)) {
        if (limits) {
            cJSON_DeleteItemFromObject(config, "limits");
        }
        limits = cJSON_CreateObject();
        if (!limits) {
            ESP_LOGW(TAG, "Failed to build limits section");
            cJSON_Delete(config);
            node_config_handler_process(topic, data, data_len, user_ctx);
            return;
        }
        cJSON_AddItemToObject(config, "limits", limits);
    }
    cJSON_DeleteItemFromObject(limits, "currentMin");
    cJSON_DeleteItemFromObject(limits, "currentMax");
    cJSON_AddNumberToObject(limits, "currentMin", EC_NODE_PUMP_CURRENT_MIN_MA);
    cJSON_AddNumberToObject(limits, "currentMax", EC_NODE_PUMP_CURRENT_MAX_MA);

    char *patched = cJSON_PrintUnformatted(config);
    cJSON_Delete(config);

    if (patched == NULL) {
        ESP_LOGW(TAG, "Failed to serialize patched config");
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    node_config_handler_process(topic, patched, (int)strlen(patched), user_ctx);
    free(patched);
}

// Wrapper для обработчика command (C-совместимый)
static void ec_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

static cJSON *ec_node_channels_callback(void *user_ctx) {
    (void)user_ctx;
    return ec_node_build_config_channels();
}

/**
 * @brief Инициализация интеграции ec_node с node_framework
 */
esp_err_t ec_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing ec_node framework integration...");

    if (!s_test_done_queue) {
        s_test_done_queue = xQueueCreate(8, sizeof(ec_node_test_done_event_t));
        if (s_test_done_queue) {
            xTaskCreate(ec_node_test_done_task, "ec_test_done", 4096, NULL, 4, NULL);
        } else {
            ESP_LOGW(TAG, "Failed to create test done queue");
        }
    }
    if (!s_pump_work_queue) {
        s_pump_work_queue = xQueueCreate(4, sizeof(uint8_t));
        if (s_pump_work_queue) {
            xTaskCreate(ec_node_pump_queue_task, "ec_pump_queue", 3072, NULL, 4, NULL);
        } else {
            ESP_LOGW(TAG, "Failed to create pump work queue");
        }
    }
    if (!s_pump_queue_mutex) {
        s_pump_queue_mutex = xSemaphoreCreateMutex();
        if (!s_pump_queue_mutex) {
            ESP_LOGW(TAG, "Failed to create pump queue mutex");
        }
    }
    if (!s_pump_retry_timer) {
        s_pump_retry_timer = xTimerCreate("ec_pump_retry", pdMS_TO_TICKS(1000), pdFALSE, NULL,
                                          ec_node_pump_retry_timer_cb);
        if (!s_pump_retry_timer) {
            ESP_LOGW(TAG, "Failed to create pump retry timer");
        }
    }

    // Инициализация node_framework
    node_framework_config_t config = {
        .node_type = "ec",
        .default_node_id = EC_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = EC_NODE_DEFAULT_GH_UID,
        .default_zone_uid = EC_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = ec_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = ec_node_publish_telemetry_callback,
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация обработчиков команд
    err = node_command_handler_register("run_pump", handle_run_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("stop_pump", handle_stop_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register stop_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("calibrate", handle_calibrate, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register calibrate handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("calibrate_ec", handle_calibrate, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register calibrate_ec handler: %s", esp_err_to_name(err));
    }

    err = node_command_handler_register("test_sensor", handle_test_sensor, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register test_sensor handler: %s", esp_err_to_name(err));
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(ec_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    node_config_handler_set_channels_callback(ec_node_channels_callback, NULL);

    ESP_LOGI(TAG, "ec_node framework integration initialized successfully");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t ec_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    return pump_driver_emergency_stop();
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 * 
 * mqtt_client - это алиас для mqtt_manager, поэтому используем mqtt_manager API
 */
void ec_node_framework_register_mqtt_handlers(void) {
    ESP_LOGI(TAG, "Registering MQTT handlers through node_framework...");
    
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(ec_node_config_handler_wrapper, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(ec_node_command_handler_wrapper, NULL);

    node_config_handler_set_mqtt_callbacks(
        ec_node_config_handler_wrapper,
        ec_node_command_handler_wrapper,
        NULL,
        NULL,
        EC_NODE_DEFAULT_NODE_ID,
        EC_NODE_DEFAULT_GH_UID,
        EC_NODE_DEFAULT_ZONE_UID
    );
    
    ESP_LOGI(TAG, "MQTT handlers registered");
}

static void ec_node_test_done_task(void *pvParameters) {
    (void) pvParameters;
    ec_node_test_done_event_t event;

    while (true) {
        if (xQueueReceive(s_test_done_queue, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        if (!event.cmd_id[0] || !event.channel_name[0]) {
            continue;
        }

        if (!event.current_valid) {
            cJSON *failed_response = node_command_handler_create_response(
                event.cmd_id,
                "FAILED",
                "current_unavailable",
                "Pump current is unavailable",
                NULL
            );
            if (failed_response) {
                char *json_str = cJSON_PrintUnformatted(failed_response);
                if (json_str) {
                    mqtt_manager_publish_command_response(event.channel_name, json_str);
                    free(json_str);
                }
                cJSON_Delete(failed_response);
            }
            node_command_handler_cache_final_status(event.cmd_id, event.channel_name, "FAILED");
            ec_node_process_pump_queue();
            continue;
        }

        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "current_ma", event.current_ma);
            cJSON_AddBoolToObject(extra, "current_valid", true);
        }

        ESP_LOGI(TAG, "Pump %s DONE current: %.2f mA", event.channel_name, event.current_ma);

        cJSON *done_response = node_command_handler_create_response(
            event.cmd_id,
            "DONE",
            NULL,
            NULL,
            extra
        );
        if (extra) {
            cJSON_Delete(extra);
        }
        if (done_response) {
            char *json_str = cJSON_PrintUnformatted(done_response);
            if (json_str) {
                mqtt_manager_publish_command_response(event.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(done_response);
        }
        node_command_handler_cache_final_status(event.cmd_id, event.channel_name, "DONE");
        ec_node_process_pump_queue();
    }
}

static void ec_node_test_done_timer_cb(TimerHandle_t timer) {
    ec_node_test_entry_t *entry = (ec_node_test_entry_t *) pvTimerGetTimerID(timer);
    if (!entry || !entry->channel_name[0]) {
        return;
    }

    if (entry->cmd_id[0] && s_test_done_queue) {
        ec_node_test_done_event_t event = {0};
        strncpy(event.channel_name, entry->channel_name, sizeof(event.channel_name) - 1);
        strncpy(event.cmd_id, entry->cmd_id, sizeof(event.cmd_id) - 1);
        event.current_ma = entry->current_ma;
        event.current_valid = entry->current_valid;
        if (xQueueSend(s_test_done_queue, &event, 0) != pdTRUE) {
            ESP_LOGW(TAG, "Test done queue full, dropping DONE response for %s", entry->channel_name);
        }
    }
}

static ec_node_test_entry_t *ec_node_get_test_entry(const char *channel, bool create) {
    if (!channel) {
        return NULL;
    }

    for (size_t i = 0; i < EC_NODE_MAX_TEST_CHANNELS; i++) {
        if (s_test_entries[i].in_use &&
            strcmp(s_test_entries[i].channel_name, channel) == 0) {
            return &s_test_entries[i];
        }
    }

    if (!create) {
        return NULL;
    }

    for (size_t i = 0; i < EC_NODE_MAX_TEST_CHANNELS; i++) {
        if (!s_test_entries[i].in_use) {
            ec_node_test_entry_t *entry = &s_test_entries[i];
            memset(entry, 0, sizeof(*entry));
            entry->in_use = true;
            strncpy(entry->channel_name, channel, sizeof(entry->channel_name) - 1);
            return entry;
        }
    }

    return NULL;
}

static void ec_node_schedule_test_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
                                       float current_ma, bool current_valid) {
    ec_node_test_entry_t *entry = ec_node_get_test_entry(channel, true);
    if (!entry) {
        ESP_LOGW(TAG, "No free test entry for channel %s", channel);
        return;
    }

    strncpy(entry->cmd_id, cmd_id ? cmd_id : "", sizeof(entry->cmd_id) - 1);
    entry->current_ma = current_ma;
    entry->current_valid = current_valid;

    if (!entry->timer) {
        entry->timer = xTimerCreate("ec_test_done", pdMS_TO_TICKS(duration_ms), pdFALSE, entry,
                                    ec_node_test_done_timer_cb);
        if (!entry->timer) {
            ESP_LOGW(TAG, "Failed to create test done timer for channel %s", channel);
            return;
        }
    }

    if (xTimerChangePeriod(entry->timer, pdMS_TO_TICKS(duration_ms), 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to start test done timer for channel %s", channel);
    }
}

static void ec_node_cancel_test_done(const char *channel, bool clear_cmd_id) {
    ec_node_test_entry_t *entry = ec_node_get_test_entry(channel, false);
    if (!entry) {
        return;
    }

    if (entry->timer) {
        xTimerStop(entry->timer, 0);
    }
    if (clear_cmd_id) {
        entry->cmd_id[0] = '\0';
    }
}

static void ec_node_get_last_pump_current(float *current_ma, bool *current_valid) {
    if (current_ma) {
        *current_ma = 0.0f;
    }
    if (current_valid) {
        *current_valid = false;
    }

    pump_driver_health_snapshot_t snapshot;
    if (pump_driver_get_health_snapshot(&snapshot) != ESP_OK) {
        return;
    }

    if (snapshot.ina_status.enabled && snapshot.ina_status.last_read_valid) {
        if (current_ma) {
            *current_ma = snapshot.ina_status.last_current_ma;
        }
        if (current_valid) {
            *current_valid = true;
        }
    }
}

static bool ec_node_any_pump_running(void) {
    pump_driver_health_snapshot_t snapshot;
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

static bool ec_node_is_channel_in_cooldown(const char *channel, uint32_t *remaining_ms) {
    if (remaining_ms) {
        *remaining_ms = 0;
    }
    if (!channel) {
        return false;
    }
    uint32_t remaining = 0;
    if (pump_driver_get_cooldown_remaining(channel, &remaining) != ESP_OK) {
        return false;
    }
    if (remaining_ms) {
        *remaining_ms = remaining;
    }
    return remaining > 0;
}

static bool ec_node_pump_queue_push(const ec_node_pump_cmd_t *cmd) {
    if (!cmd || !cmd->channel_name[0]) {
        return false;
    }
    if (!s_pump_queue_mutex || xSemaphoreTake(s_pump_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }

    if (s_pump_queue_count >= EC_NODE_PUMP_QUEUE_MAX) {
        xSemaphoreGive(s_pump_queue_mutex);
        return false;
    }

    s_pump_queue[s_pump_queue_tail] = *cmd;
    s_pump_queue_tail = (s_pump_queue_tail + 1) % EC_NODE_PUMP_QUEUE_MAX;
    s_pump_queue_count++;

    xSemaphoreGive(s_pump_queue_mutex);
    return true;
}

static bool ec_node_pump_queue_pop(ec_node_pump_cmd_t *cmd) {
    if (!cmd) {
        return false;
    }
    if (!s_pump_queue_mutex || xSemaphoreTake(s_pump_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }

    if (s_pump_queue_count == 0) {
        xSemaphoreGive(s_pump_queue_mutex);
        return false;
    }

    *cmd = s_pump_queue[s_pump_queue_head];
    memset(&s_pump_queue[s_pump_queue_head], 0, sizeof(s_pump_queue[s_pump_queue_head]));
    s_pump_queue_head = (s_pump_queue_head + 1) % EC_NODE_PUMP_QUEUE_MAX;
    s_pump_queue_count--;

    xSemaphoreGive(s_pump_queue_mutex);
    return true;
}

static size_t ec_node_pump_queue_count(void) {
    if (!s_pump_queue_mutex) {
        return 0;
    }
    if (xSemaphoreTake(s_pump_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return 0;
    }
    size_t count = s_pump_queue_count;
    xSemaphoreGive(s_pump_queue_mutex);
    return count;
}

static size_t ec_node_pump_queue_remove_channel(const char *channel) {
    if (!channel || !s_pump_queue_mutex) {
        return 0;
    }
    if (xSemaphoreTake(s_pump_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return 0;
    }

    ec_node_pump_cmd_t new_queue[EC_NODE_PUMP_QUEUE_MAX] = {0};
    size_t new_count = 0;
    size_t removed = 0;

    for (size_t i = 0; i < s_pump_queue_count; i++) {
        size_t idx = (s_pump_queue_head + i) % EC_NODE_PUMP_QUEUE_MAX;
        if (strncmp(s_pump_queue[idx].channel_name, channel, EC_NODE_MAX_CHANNEL_NAME_LEN) == 0) {
            removed++;
            continue;
        }
        if (new_count < EC_NODE_PUMP_QUEUE_MAX) {
            new_queue[new_count++] = s_pump_queue[idx];
        }
    }

    memset(s_pump_queue, 0, sizeof(s_pump_queue));
    for (size_t i = 0; i < new_count; i++) {
        s_pump_queue[i] = new_queue[i];
    }
    s_pump_queue_head = 0;
    s_pump_queue_tail = new_count % EC_NODE_PUMP_QUEUE_MAX;
    s_pump_queue_count = new_count;

    xSemaphoreGive(s_pump_queue_mutex);
    return removed;
}

static void ec_node_process_pump_queue(void) {
    if (ec_node_any_pump_running()) {
        return;
    }

    ec_node_pump_cmd_t cmd = {0};
    size_t to_process = ec_node_pump_queue_count();
    uint32_t min_cooldown_ms = 0;
    while (to_process-- > 0 && ec_node_pump_queue_pop(&cmd)) {
        uint32_t cooldown_remaining_ms = 0;
        if (ec_node_is_channel_in_cooldown(cmd.channel_name, &cooldown_remaining_ms)) {
            if (!ec_node_pump_queue_push(&cmd)) {
                cJSON *failed_response = node_command_handler_create_response(
                    cmd.cmd_id[0] ? cmd.cmd_id : NULL,
                    "FAILED",
                    "pump_queue_full",
                    "Pump queue is full",
                    NULL
                );
                if (failed_response) {
                    char *json_str = cJSON_PrintUnformatted(failed_response);
                    if (json_str) {
                        mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                        free(json_str);
                    }
                    cJSON_Delete(failed_response);
                }
                if (cmd.cmd_id[0]) {
                    node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "FAILED");
                }
            }
            if (cooldown_remaining_ms > 0) {
                if (min_cooldown_ms == 0 || cooldown_remaining_ms < min_cooldown_ms) {
                    min_cooldown_ms = cooldown_remaining_ms;
                }
            }
            continue;
        }

        float current_ma = 0.0f;
        bool current_valid = false;
        esp_err_t err = ec_node_start_pump_command(cmd.channel_name, cmd.duration_ms,
                                                  &current_ma, &current_valid);
        if (err == ESP_OK) {
            ec_node_schedule_test_done(cmd.channel_name, cmd.cmd_id, cmd.duration_ms,
                                       current_ma, current_valid);
            ESP_LOGI(TAG, "Pump %s started from queue for %lu ms", cmd.channel_name,
                     (unsigned long)cmd.duration_ms);
            return;
        }

        cJSON *failed_response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "pump_error",
            "Failed to run pump",
            NULL
        );
        cJSON *mapped_response = ec_node_create_pump_failed_response(
            cmd.cmd_id[0] ? cmd.cmd_id : NULL,
            cmd.channel_name,
            err
        );
        if (mapped_response) {
            if (failed_response) {
                cJSON_Delete(failed_response);
            }
            failed_response = mapped_response;
        }
        if (failed_response) {
            char *json_str = cJSON_PrintUnformatted(failed_response);
            if (json_str) {
                mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(failed_response);
        }
        if (cmd.cmd_id[0]) {
            node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "FAILED");
        }
    }
    if (min_cooldown_ms > 0) {
        ec_node_schedule_pump_retry(min_cooldown_ms);
    }
}

static void ec_node_schedule_pump_retry(uint32_t delay_ms) {
    if (!s_pump_retry_timer) {
        return;
    }
    if (delay_ms == 0) {
        delay_ms = 1;
    }
    if (xTimerChangePeriod(s_pump_retry_timer, pdMS_TO_TICKS(delay_ms), 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to schedule pump retry timer");
        return;
    }
    xTimerStart(s_pump_retry_timer, 0);
}

static void ec_node_pump_retry_timer_cb(TimerHandle_t timer) {
    (void)timer;
    ec_node_signal_pump_queue_process();
}

static esp_err_t ec_node_start_pump_command(const char *channel, uint32_t duration_ms,
                                            float *current_ma, bool *current_valid) {
    esp_err_t err = pump_driver_run(channel, duration_ms);
    if (err != ESP_OK) {
        return err;
    }

    if (current_ma) {
        *current_ma = 0.0f;
    }
    if (current_valid) {
        *current_valid = false;
    }

    float current_local = 0.0f;
    bool current_ok = false;
    ec_node_get_last_pump_current(&current_local, &current_ok);
    if (!current_ok) {
        ESP_LOGW(TAG, "Pump %s started but current is unavailable", channel);
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "pump_driver", ESP_ERR_INVALID_STATE,
                                       "Pump current is unavailable");
        pump_driver_stop(channel);
        return ESP_ERR_INVALID_STATE;
    }

    if (current_ma) {
        *current_ma = current_local;
    }
    if (current_valid) {
        *current_valid = current_ok;
    }

    ESP_LOGI(TAG, "Pump %s current: %.2f mA", channel, current_local);
    return ESP_OK;
}

static void ec_node_pump_queue_task(void *pvParameters) {
    (void) pvParameters;
    uint8_t token = 0;

    while (true) {
        if (xQueueReceive(s_pump_work_queue, &token, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        ec_node_process_pump_queue();
    }
}

static void ec_node_signal_pump_queue_process(void) {
    if (!s_pump_work_queue) {
        return;
    }
    uint8_t token = 1;
    xQueueSend(s_pump_work_queue, &token, 0);
}

static cJSON *ec_node_create_pump_failed_response(const char *cmd_id, const char *channel, esp_err_t err) {
    const char *error_code = "pump_error";
    const char *error_message = "Failed to run pump";

    if (err == ESP_ERR_INVALID_STATE) {
        uint32_t cooldown_remaining_ms = 0;
        if (ec_node_is_channel_in_cooldown(channel, &cooldown_remaining_ms) && cooldown_remaining_ms > 0) {
            error_code = "cooldown_active";
            error_message = "Pump is in cooldown";
        } else if (pump_driver_is_running(channel) || ec_node_any_pump_running()) {
            error_code = "pump_busy";
            error_message = "Pump is already running";
        } else {
            error_code = "current_unavailable";
            error_message = "Pump current is unavailable";
        }
    }

    return node_command_handler_create_response(
        cmd_id,
        "FAILED",
        error_code,
        error_message,
        NULL
    );
}
