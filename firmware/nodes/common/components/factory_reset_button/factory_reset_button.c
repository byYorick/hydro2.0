/**
 * @file factory_reset_button.c
 * @brief Long-press button handler for full NVS wipe + reboot to setup
 */

#include "factory_reset_button.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

// Defaults target BOOT button (GPIO0) on ESP32-DevKit style boards
#define FACTORY_RESET_DEFAULT_GPIO            GPIO_NUM_0
#define FACTORY_RESET_DEFAULT_ACTIVE_LOW      true
#define FACTORY_RESET_DEFAULT_PULL_UP         true
#define FACTORY_RESET_DEFAULT_PULL_DOWN       false
#define FACTORY_RESET_DEFAULT_HOLD_MS         20000U
#define FACTORY_RESET_DEFAULT_POLL_INTERVAL   50U

static const char *TAG = "factory_reset_btn";

typedef struct {
    factory_reset_button_config_t cfg;
    bool initialized;
    TaskHandle_t task_handle;
} factory_reset_button_ctx_t;

static factory_reset_button_ctx_t s_ctx = {0};

static void do_factory_reset(void) {
    ESP_LOGW(TAG, "Factory reset triggered: erasing NVS and rebooting into setup mode");

    // Give logs a moment to flush
    vTaskDelay(pdMS_TO_TICKS(100));

    nvs_flash_deinit();
    esp_err_t err = nvs_flash_erase();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to erase NVS: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "NVS erased successfully");
    }

    vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();
}

static void factory_reset_button_task(void *arg) {
    (void)arg;
    uint32_t pressed_ms = 0;
    uint32_t last_log_ms = 0;

    while (1) {
        int level = gpio_get_level(s_ctx.cfg.gpio_num);
        bool active = s_ctx.cfg.active_level_low ? (level == 0) : (level != 0);

        if (active) {
            pressed_ms += s_ctx.cfg.poll_interval_ms;

            // Log progress every 5 seconds to aid debugging long presses
            if (pressed_ms / 5000 != last_log_ms / 5000) {
                ESP_LOGI(TAG, "Reset button held for %u ms (target %u ms)", pressed_ms, s_ctx.cfg.hold_time_ms);
                last_log_ms = pressed_ms;
            }

            if (pressed_ms >= s_ctx.cfg.hold_time_ms) {
                do_factory_reset();
            }
        } else {
            pressed_ms = 0;
            last_log_ms = 0;
        }

        vTaskDelay(pdMS_TO_TICKS(s_ctx.cfg.poll_interval_ms));
    }
}

esp_err_t factory_reset_button_init(const factory_reset_button_config_t *config) {
    if (s_ctx.initialized) {
        ESP_LOGW(TAG, "factory_reset_button already initialized");
        return ESP_OK;
    }

    // Apply defaults
    s_ctx.cfg.gpio_num = FACTORY_RESET_DEFAULT_GPIO;
    s_ctx.cfg.active_level_low = FACTORY_RESET_DEFAULT_ACTIVE_LOW;
    s_ctx.cfg.pull_up = FACTORY_RESET_DEFAULT_PULL_UP;
    s_ctx.cfg.pull_down = FACTORY_RESET_DEFAULT_PULL_DOWN;
    s_ctx.cfg.hold_time_ms = FACTORY_RESET_DEFAULT_HOLD_MS;
    s_ctx.cfg.poll_interval_ms = FACTORY_RESET_DEFAULT_POLL_INTERVAL;

    if (config != NULL) {
        s_ctx.cfg = *config;
    }

    if (s_ctx.cfg.hold_time_ms == 0) {
        s_ctx.cfg.hold_time_ms = FACTORY_RESET_DEFAULT_HOLD_MS;
    }
    if (s_ctx.cfg.poll_interval_ms == 0) {
        s_ctx.cfg.poll_interval_ms = FACTORY_RESET_DEFAULT_POLL_INTERVAL;
    }

    if (!GPIO_IS_VALID_GPIO(s_ctx.cfg.gpio_num)) {
        ESP_LOGW(TAG, "Invalid GPIO for factory reset button (%d), component disabled", s_ctx.cfg.gpio_num);
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << s_ctx.cfg.gpio_num,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = s_ctx.cfg.pull_up ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = s_ctx.cfg.pull_down ? GPIO_PULLDOWN_ENABLE : GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure GPIO%d for reset button: %s", s_ctx.cfg.gpio_num, esp_err_to_name(err));
        return err;
    }

    BaseType_t task_created = xTaskCreate(factory_reset_button_task, "factory_reset_btn", 3072, NULL, 4, &s_ctx.task_handle);
    if (task_created != pdPASS) {
        ESP_LOGE(TAG, "Failed to create factory reset button task");
        return ESP_ERR_NO_MEM;
    }

    s_ctx.initialized = true;
    ESP_LOGI(TAG, "Factory reset button armed on GPIO%d (active_%s, hold %u ms)", 
             s_ctx.cfg.gpio_num,
             s_ctx.cfg.active_level_low ? "low" : "high",
             s_ctx.cfg.hold_time_ms);
    return ESP_OK;
}
