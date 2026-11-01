/**
 * @file actuator_failsafe.c
 * @brief Опрос аппаратного E-STOP и защёлка для ph/ec/pump.
 */

#include "actuator_failsafe.h"
#include "actuator_failsafe_logic.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "actuator_failsafe";

#define ACTUATOR_FAILSAFE_TASK_STACK 3072
#define ACTUATOR_FAILSAFE_TASK_PRIORITY 8

static actuator_failsafe_logic_t s_logic;
static actuator_failsafe_safe_state_fn s_safe_state_cb = NULL;
static void *s_safe_state_ctx = NULL;
static int s_gpio_pin = -1;
static bool s_active_low = true;
static int64_t s_debounce_us = (int64_t)ACTUATOR_FAILSAFE_DEFAULT_DEBOUNCE_MS * 1000;
static volatile bool s_latched = false;
static bool s_ready = false;
static TaskHandle_t s_task = NULL;

static bool actuator_failsafe_read_pressed(void)
{
    int raw = gpio_get_level((gpio_num_t)s_gpio_pin);
    return s_active_low ? (raw == 0) : (raw != 0);
}

esp_err_t actuator_failsafe_force_safe_state(void)
{
    if (s_safe_state_cb == NULL) {
        ESP_LOGW(TAG, "E-STOP safe-state callback is not set");
        return ESP_ERR_INVALID_STATE;
    }
    esp_err_t err = s_safe_state_cb(s_safe_state_ctx);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "E-STOP safe-state callback failed: %s", esp_err_to_name(err));
    }
    return err;
}

static void actuator_failsafe_apply_edge(actuator_failsafe_edge_t edge)
{
    s_latched = s_logic.latched;
    if (edge == ACTUATOR_FAILSAFE_EDGE_PRESSED) {
        ESP_LOGW(TAG, "E-STOP latched on GPIO %d", s_gpio_pin);
        (void)actuator_failsafe_force_safe_state();
        return;
    }
    if (edge == ACTUATOR_FAILSAFE_EDGE_HELD) {
        (void)actuator_failsafe_force_safe_state();
        return;
    }
    if (edge == ACTUATOR_FAILSAFE_EDGE_RELEASED) {
        ESP_LOGW(TAG, "E-STOP released; actuators stay OFF until a new command");
    }
}

static void actuator_failsafe_poll(void)
{
    if (!s_ready) {
        return;
    }
    bool pressed = actuator_failsafe_read_pressed();
    actuator_failsafe_edge_t edge = actuator_failsafe_logic_step(
        &s_logic,
        pressed,
        esp_timer_get_time(),
        s_debounce_us
    );
    actuator_failsafe_apply_edge(edge);
}

static void actuator_failsafe_task(void *arg)
{
    (void)arg;
    while (true) {
        actuator_failsafe_poll();
        vTaskDelay(pdMS_TO_TICKS(ACTUATOR_FAILSAFE_POLL_PERIOD_MS));
    }
}

esp_err_t actuator_failsafe_init(const actuator_failsafe_config_t *config)
{
    if (s_ready) {
        return ESP_OK;
    }
    if (config == NULL || !GPIO_IS_VALID_GPIO(config->gpio_pin)) {
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << (uint32_t)config->gpio_pin,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = config->active_low ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = config->active_low ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure E-STOP GPIO %d: %s", config->gpio_pin, esp_err_to_name(err));
        return err;
    }

    s_gpio_pin = config->gpio_pin;
    s_active_low = config->active_low;
    s_safe_state_cb = config->safe_state_cb;
    s_safe_state_ctx = config->safe_state_ctx;
    uint32_t debounce_ms = config->debounce_ms > 0 ? config->debounce_ms : ACTUATOR_FAILSAFE_DEFAULT_DEBOUNCE_MS;
    s_debounce_us = (int64_t)debounce_ms * 1000;

    actuator_failsafe_logic_reset(&s_logic);
    bool pressed = actuator_failsafe_read_pressed();
    actuator_failsafe_edge_t edge = actuator_failsafe_logic_step(
        &s_logic,
        pressed,
        esp_timer_get_time(),
        s_debounce_us
    );
    s_latched = s_logic.latched;
    s_ready = true;

    /* Boot/reset: выходы в safe-OFF независимо от кнопки. */
    esp_err_t safe_err = actuator_failsafe_force_safe_state();
    if (edge == ACTUATOR_FAILSAFE_EDGE_PRESSED) {
        ESP_LOGW(TAG, "E-STOP already pressed at boot, GPIO %d latched", s_gpio_pin);
    } else if (safe_err != ESP_OK) {
        ESP_LOGW(TAG, "Boot safe-state incomplete: %s", esp_err_to_name(safe_err));
    }

    if (s_task == NULL) {
        BaseType_t created = xTaskCreate(
            actuator_failsafe_task,
            "act_failsafe",
            ACTUATOR_FAILSAFE_TASK_STACK,
            NULL,
            ACTUATOR_FAILSAFE_TASK_PRIORITY,
            &s_task
        );
        if (created != pdPASS) {
            s_task = NULL;
            ESP_LOGE(TAG, "Failed to start E-STOP poll task");
            return ESP_ERR_NO_MEM;
        }
    }

    ESP_LOGI(TAG, "E-STOP input GPIO %d active_%s debounce %lu ms",
             s_gpio_pin,
             s_active_low ? "low" : "high",
             (unsigned long)debounce_ms);
    return ESP_OK;
}

bool actuator_failsafe_is_latched(void)
{
    return s_ready && s_latched;
}
