/**
 * @file factory_reset_button.h
 * @brief Long-press button handler that erases NVS and restarts into setup mode
 *
 * Note: The EN/RST button on devkits cannot be sampled (it just reboots the chip).
 * Use a GPIO-backed user/BOOT button and hold it for the configured duration.
 */

#ifndef FACTORY_RESET_BUTTON_H
#define FACTORY_RESET_BUTTON_H

#include "esp_err.h"
#include "driver/gpio.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    gpio_num_t gpio_num;        // GPIO to monitor (default GPIO0 / BOOT on devkit)
    bool active_level_low;      // true if button pulls the line low when pressed
    bool pull_up;               // enable internal pull-up
    bool pull_down;             // enable internal pull-down
    uint32_t hold_time_ms;      // how long the button must be held to trigger
    uint32_t poll_interval_ms;  // sampling interval
} factory_reset_button_config_t;

/**
 * @brief Start background task that waits for long press and erases NVS.
 *
 * On trigger: deinit NVS, erase it, log a message, and call esp_restart().
 *
 * @param config Optional configuration, NULL to use defaults.
 * @return ESP_OK on start, error otherwise.
 */
esp_err_t factory_reset_button_init(const factory_reset_button_config_t *config);

#ifdef __cplusplus
}
#endif

#endif // FACTORY_RESET_BUTTON_H
