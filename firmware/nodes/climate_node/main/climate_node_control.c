#include "climate_node_control.h"

#include "climate_control_logic.h"
#include "climate_node_defaults.h"
#include "actuator_failsafe.h"
#include "node_command_handler.h"
#include "relay_driver.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "cJSON.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *TAG = "climate_ctrl";

#define CLIMATE_AIR_STALE_US (30LL * 1000000LL)
#define CLIMATE_TICK_US 100000

typedef struct {
    vent_drive_t drive;
    gpio_num_t open_gpio;
    gpio_num_t close_gpio;
    gpio_num_t closed_limit_gpio;
    char channel[24];
    char cmd_id[40];
    bool response_pending;
    bool failed;
} vent_hw_t;

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static vent_hw_t s_vents[2];
static exhaust_hyst_t s_fan;
static climate_safe_mode_t s_safe_mode = CLIMATE_SAFE_VENTILATE_ABOVE;
static float s_overheat_c = 32.0f;
static float s_ventilate_above_c = 25.0f;
static int s_failsafe_open_pct = 100;
static bool s_air_valid = false;
static float s_air_c = 0.0f;
static int64_t s_air_us = 0;
static bool s_ready = false;
static esp_timer_handle_t s_timer = NULL;

static bool channel_index(const char *channel, int *index)
{
    if (channel == NULL) {
        return false;
    }
    if (strcmp(channel, "roof_vent_left") == 0) {
        *index = 0;
        return true;
    }
    if (strcmp(channel, "roof_vent_right") == 0) {
        *index = 1;
        return true;
    }
    return false;
}

static void load_policy(void)
{
    static char json[CONFIG_STORAGE_MAX_JSON_SIZE];
    cJSON *root;
    cJSON *block;
    cJSON *item;

    s_fan.on_c = 25.0f;
    s_fan.off_c = 23.0f;
    s_overheat_c = 32.0f;
    s_ventilate_above_c = 25.0f;
    s_failsafe_open_pct = 100;
    s_safe_mode = CLIMATE_SAFE_VENTILATE_ABOVE;
    if (config_storage_get_json(json, sizeof(json)) != ESP_OK) {
        return;
    }
    root = cJSON_Parse(json);
    if (root == NULL) {
        return;
    }
    block = cJSON_GetObjectItem(root, "climate_control");
    if (!cJSON_IsObject(block)) {
        cJSON_Delete(root);
        return;
    }
    item = cJSON_GetObjectItem(block, "exhaust_on_c");
    if (cJSON_IsNumber(item)) {
        s_fan.on_c = (float)cJSON_GetNumberValue(item);
    }
    item = cJSON_GetObjectItem(block, "exhaust_off_c");
    if (cJSON_IsNumber(item)) {
        s_fan.off_c = (float)cJSON_GetNumberValue(item);
    }
    item = cJSON_GetObjectItem(block, "overheat_c");
    if (cJSON_IsNumber(item)) {
        s_overheat_c = (float)cJSON_GetNumberValue(item);
    }
    item = cJSON_GetObjectItem(block, "ventilate_above_c");
    if (cJSON_IsNumber(item)) {
        s_ventilate_above_c = (float)cJSON_GetNumberValue(item);
    }
    item = cJSON_GetObjectItem(block, "failsafe_open_pct");
    if (cJSON_IsNumber(item)) {
        s_failsafe_open_pct = (int)cJSON_GetNumberValue(item);
    }
    item = cJSON_GetObjectItem(block, "travel_full_ms");
    if (cJSON_IsNumber(item) && cJSON_GetNumberValue(item) > 0.0) {
        uint32_t travel = (uint32_t)cJSON_GetNumberValue(item);
        s_vents[0].drive.travel_full_ms = travel;
        s_vents[1].drive.travel_full_ms = travel;
    }
    item = cJSON_GetObjectItem(block, "safe_mode");
    if (cJSON_IsString(item) && strcmp(item->valuestring, "all_off") == 0) {
        s_safe_mode = CLIMATE_SAFE_ALL_OFF;
    }
    cJSON_Delete(root);
}

static bool air_is_fresh(float *temp_out)
{
    int64_t now = esp_timer_get_time();
    if (!s_air_valid || (now - s_air_us) > CLIMATE_AIR_STALE_US || !isfinite(s_air_c)) {
        return false;
    }
    if (temp_out != NULL) {
        *temp_out = s_air_c;
    }
    return true;
}

static void set_motor_gpio(const vent_hw_t *vent, vent_motor_t motor)
{
    if (motor == VENT_OPEN) {
        gpio_set_level(vent->close_gpio, 0);
        gpio_set_level(vent->open_gpio, 1);
        return;
    }
    if (motor == VENT_CLOSE) {
        gpio_set_level(vent->open_gpio, 0);
        gpio_set_level(vent->close_gpio, 1);
        return;
    }
    gpio_set_level(vent->open_gpio, 0);
    gpio_set_level(vent->close_gpio, 0);
}

static void set_exhaust(bool on)
{
    relay_state_t state = on ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
    relay_state_t probe;
    bool relay_used = false;

    if (relay_driver_get_state("fan_A", &probe) == ESP_OK) {
        (void)relay_driver_set_state("fan_A", state);
        relay_used = true;
    }
    if (relay_driver_get_state("fan_B", &probe) == ESP_OK) {
        (void)relay_driver_set_state("fan_B", state);
        relay_used = true;
    }
    if (!relay_used) {
        gpio_set_level(CLIMATE_EXHAUST_GPIO, on ? 1 : 0);
    }
}

static void publish_terminal(const char *channel, const char *cmd_id, bool failed)
{
    cJSON *extra = NULL;
    cJSON *response;
    char *json;

    if (cmd_id == NULL || cmd_id[0] == '\0' || !mqtt_manager_is_connected()) {
        return;
    }
    if (!failed) {
        extra = cJSON_CreateObject();
        if (extra != NULL) {
            cJSON_AddStringToObject(extra, "cmd", "set_position");
        }
    }
    response = node_command_handler_create_response(
        cmd_id,
        failed ? "ERROR" : "DONE",
        failed ? "vent_travel_failed" : NULL,
        failed ? "Vent move timed out or the limit was not reached" : NULL,
        extra);
    if (extra != NULL) {
        cJSON_Delete(extra);
    }
    if (response == NULL) {
        return;
    }
    json = cJSON_PrintUnformatted(response);
    cJSON_Delete(response);
    if (json == NULL) {
        return;
    }
    (void)mqtt_manager_publish_command_response(channel, json);
    free(json);
    node_command_handler_cache_final_status(cmd_id, channel, failed ? "ERROR" : "DONE");
}

static bool limit_closed(const vent_hw_t *vent)
{
    if (vent->closed_limit_gpio < 0) {
        return false;
    }
    return gpio_get_level(vent->closed_limit_gpio) == 0;
}

static void control_tick(void *arg)
{
    climate_fs_input_t in;
    climate_fs_output_t out;
    exhaust_level_t level;
    float temp = 0.0f;
    bool fresh;
    bool estop;
    int i;

    (void)arg;
    if (!s_ready) {
        return;
    }
    estop = actuator_failsafe_is_latched();
    fresh = air_is_fresh(&temp);
    level = exhaust_hysteresis_step(&s_fan, fresh && !estop, temp);
    in.estop = estop;
    in.driver_ok = true;
    in.sensor_valid = fresh;
    in.temp_c = temp;
    in.link_up = mqtt_manager_is_connected();
    in.safe_mode = s_safe_mode;
    in.ventilate_above_c = s_ventilate_above_c;
    in.overheat_c = s_overheat_c;
    in.failsafe_open_pct = s_failsafe_open_pct;
    in.cool_close_c = s_fan.off_c;
    climate_failsafe_decide(&in, level == EXHAUST_ON, &out);

    {
        bool closed[2] = {limit_closed(&s_vents[0]), limit_closed(&s_vents[1])};
        vent_motor_t motors[2] = {VENT_STOP, VENT_STOP};

        taskENTER_CRITICAL(&s_mux);
        if (out.deenergize_all || estop) {
            s_fan.fan_on = false;
            for (i = 0; i < 2; i++) {
                if (s_vents[i].response_pending) {
                    s_vents[i].failed = true;
                }
                vent_drive_halt(&s_vents[i].drive);
            }
        } else if (out.move_vents) {
            for (i = 0; i < 2; i++) {
                if (s_vents[i].response_pending) {
                    s_vents[i].failed = true;
                }
                vent_drive_override(&s_vents[i].drive, out.vent_target_pct);
            }
        }
        for (i = 0; i < 2; i++) {
            bool was = s_vents[i].drive.moving;
            (void)vent_drive_step(&s_vents[i].drive, 100u, closed[i], false, false);
            if (was && !s_vents[i].drive.moving && s_vents[i].response_pending) {
                s_vents[i].failed = s_vents[i].failed || s_vents[i].drive.fault;
            }
            motors[i] = s_vents[i].drive.motor;
        }
        taskEXIT_CRITICAL(&s_mux);

        if (out.deenergize_all || estop) {
            set_motor_gpio(&s_vents[0], VENT_STOP);
            set_motor_gpio(&s_vents[1], VENT_STOP);
            set_exhaust(false);
        } else {
            set_motor_gpio(&s_vents[0], motors[0]);
            set_motor_gpio(&s_vents[1], motors[1]);
            set_exhaust(out.exhaust_on);
        }
    }

    for (i = 0; i < 2; i++) {
        bool publish = false;
        bool failed = false;
        char cmd_id[40];
        char channel[24];

        taskENTER_CRITICAL(&s_mux);
        if (s_vents[i].response_pending && !s_vents[i].drive.moving) {
            publish = true;
            failed = s_vents[i].failed || s_vents[i].drive.fault;
            strncpy(cmd_id, s_vents[i].cmd_id, sizeof(cmd_id) - 1);
            cmd_id[sizeof(cmd_id) - 1] = '\0';
            strncpy(channel, s_vents[i].channel, sizeof(channel) - 1);
            channel[sizeof(channel) - 1] = '\0';
            if (mqtt_manager_is_connected()) {
                s_vents[i].response_pending = false;
            }
        }
        taskEXIT_CRITICAL(&s_mux);
        if (publish) {
            publish_terminal(channel, cmd_id, failed);
        }
    }
}

static esp_err_t handle_set_position(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx)
{
    const cJSON *position;
    const cJSON *step;
    const char *cmd_id;
    int index = 0;
    int requested;
    int target;
    bool has_step;
    double step_value = 0.0;
    climate_cmd_status_t valid;
    climate_cmd_status_t started;
    cJSON *extra = NULL;

    (void)user_ctx;
    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    cmd_id = node_command_handler_get_cmd_id(params);
    if (!channel_index(channel, &index)) {
        *response = node_command_handler_create_response(
            cmd_id, "INVALID", "invalid_channel", "set_position is supported on roof_vent_left and roof_vent_right", NULL);
        return ESP_ERR_INVALID_ARG;
    }
    if (actuator_failsafe_is_latched()) {
        *response = node_command_handler_create_response(
            cmd_id, "ERROR", "estop_active", "E-STOP is latched; actuators stay off", NULL);
        return ESP_ERR_INVALID_STATE;
    }
    position = cJSON_GetObjectItem(params, "position_pct");
    step = cJSON_GetObjectItem(params, "max_step_pct");
    has_step = step != NULL;
    valid = climate_set_position_validate(
        cJSON_IsNumber(position),
        cJSON_IsNumber(position) ? cJSON_GetNumberValue(position) : NAN,
        has_step,
        cJSON_IsNumber(step) ? cJSON_GetNumberValue(step) : NAN);
    if (valid != CLIMATE_CMD_OK) {
        *response = node_command_handler_create_response(
            cmd_id, "INVALID", "invalid_params", "position_pct must be 0..100; max_step_pct if present must be 0..100", NULL);
        return ESP_ERR_INVALID_ARG;
    }
    requested = (int)lround(cJSON_GetNumberValue(position));
    if (has_step && cJSON_IsNumber(step)) {
        step_value = cJSON_GetNumberValue(step);
    }

    taskENTER_CRITICAL(&s_mux);
    if (s_vents[index].drive.moving) {
        taskEXIT_CRITICAL(&s_mux);
        *response = node_command_handler_create_response(
            cmd_id, "BUSY", "vent_busy", "Vent actuator is already moving", NULL);
        return ESP_ERR_INVALID_STATE;
    }
    s_vents[index].drive.fault = false;
    if (s_vents[index].drive.known) {
        target = climate_position_apply_step(
            s_vents[index].drive.position_pct,
            requested,
            has_step && cJSON_IsNumber(step),
            (int)lround(step_value));
    } else {
        target = requested;
    }
    started = vent_drive_command(&s_vents[index].drive, target, 0);
    if (started == CLIMATE_CMD_OK) {
        snprintf(s_vents[index].cmd_id, sizeof(s_vents[index].cmd_id), "%s", cmd_id != NULL ? cmd_id : "");
        snprintf(s_vents[index].channel, sizeof(s_vents[index].channel), "%s", channel);
        s_vents[index].response_pending = s_vents[index].cmd_id[0] != '\0';
        s_vents[index].failed = false;
    }
    taskEXIT_CRITICAL(&s_mux);

    if (started == CLIMATE_CMD_NO_EFFECT) {
        extra = cJSON_CreateObject();
        if (extra != NULL) {
            cJSON_AddBoolToObject(extra, "already_at_target", true);
            cJSON_AddNumberToObject(extra, "position_pct", target);
        }
        *response = node_command_handler_create_response(cmd_id, "DONE", NULL, NULL, extra);
        if (extra != NULL) {
            cJSON_Delete(extra);
        }
        return ESP_OK;
    }
    if (started != CLIMATE_CMD_OK) {
        *response = node_command_handler_create_response(
            cmd_id, "ERROR", "vent_fault", "Vent drive refused the position", NULL);
        return ESP_ERR_INVALID_STATE;
    }
    *response = node_command_handler_create_response(cmd_id, "ACK", NULL, NULL, NULL);
    return ESP_OK;
}

static esp_err_t estop_safe_state(void *ctx)
{
    (void)ctx;
    climate_node_control_apply_now();
    return ESP_OK;
}

static esp_err_t config_output(gpio_num_t pin, int level)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << pin,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&cfg);
    if (err == ESP_OK) {
        gpio_set_level(pin, level);
    }
    return err;
}

static esp_err_t config_limit(gpio_num_t pin)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << pin,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&cfg);
}

esp_err_t climate_node_control_init(void)
{
    const esp_timer_create_args_t timer_args = {
        .callback = control_tick,
        .name = "climate_ctrl",
    };
    actuator_failsafe_config_t estop = {
        .gpio_pin = CLIMATE_ESTOP_GPIO,
        .active_low = true,
        .debounce_ms = 80,
        .safe_state_cb = estop_safe_state,
        .safe_state_ctx = NULL,
    };
    esp_err_t err;
    int i;

    memset(s_vents, 0, sizeof(s_vents));
    snprintf(s_vents[0].channel, sizeof(s_vents[0].channel), "roof_vent_left");
    snprintf(s_vents[1].channel, sizeof(s_vents[1].channel), "roof_vent_right");
    s_vents[0].open_gpio = CLIMATE_VENT_LEFT_OPEN_GPIO;
    s_vents[0].close_gpio = CLIMATE_VENT_LEFT_CLOSE_GPIO;
    s_vents[0].closed_limit_gpio = CLIMATE_VENT_LEFT_CLOSED_LIMIT_GPIO;
    s_vents[1].open_gpio = CLIMATE_VENT_RIGHT_OPEN_GPIO;
    s_vents[1].close_gpio = CLIMATE_VENT_RIGHT_CLOSE_GPIO;
    s_vents[1].closed_limit_gpio = CLIMATE_VENT_RIGHT_CLOSED_LIMIT_GPIO;
    for (i = 0; i < 2; i++) {
        vent_drive_init(&s_vents[i].drive, 60000u, 5000u);
        (void)config_output(s_vents[i].open_gpio, 0);
        (void)config_output(s_vents[i].close_gpio, 0);
        (void)config_limit(s_vents[i].closed_limit_gpio);
    }
    (void)config_output(CLIMATE_EXHAUST_GPIO, 0);
    load_policy();
    err = node_command_handler_register("set_position", handle_set_position, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "set_position register failed: %s", esp_err_to_name(err));
        return err;
    }
    err = esp_timer_create(&timer_args, &s_timer);
    if (err != ESP_OK) {
        return err;
    }
    s_ready = true;
    err = esp_timer_start_periodic(s_timer, CLIMATE_TICK_US);
    if (err != ESP_OK) {
        return err;
    }
    err = actuator_failsafe_init(&estop);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "E-STOP init failed: %s", esp_err_to_name(err));
    }
    ESP_LOGI(TAG, "Climate control ready (vents + exhaust hysteresis)");
    return ESP_OK;
}

void climate_node_control_set_air(bool valid, float temp_c)
{
    s_air_valid = valid && isfinite(temp_c);
    if (s_air_valid) {
        s_air_c = temp_c;
    }
    s_air_us = esp_timer_get_time();
}

void climate_node_control_apply_now(void)
{
    load_policy();
    control_tick(NULL);
}

bool climate_node_control_estop_latched(void)
{
    return actuator_failsafe_is_latched();
}

bool climate_node_control_ventilation_safe(void)
{
    return s_safe_mode == CLIMATE_SAFE_VENTILATE_ABOVE && !actuator_failsafe_is_latched();
}
