/**
 * @file climate_node_init_steps.h
 * @brief Модульная система инициализации climate_node
 * 
 * Разбивает монолитную инициализацию на отдельные шаги,
 * каждый из которых может быть выполнен независимо и повторно.
 */

#ifndef CLIMATE_NODE_INIT_STEPS_H
#define CLIMATE_NODE_INIT_STEPS_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Результат инициализации шага
 */
typedef struct {
    esp_err_t err;
    bool component_initialized;
    const char *component_name;
} climate_node_init_step_result_t;

/**
 * @brief Контекст инициализации
 */
typedef struct {
    bool show_oled_steps;  // Показывать шаги на OLED
    void *user_ctx;
} climate_node_init_context_t;

// Шаг 1: Config Storage
esp_err_t climate_node_init_step_config_storage(climate_node_init_context_t *ctx, 
                                                climate_node_init_step_result_t *result);

// Шаг 2: Wi-Fi Manager
esp_err_t climate_node_init_step_wifi(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result);

// Шаг 3: I2C Buses
esp_err_t climate_node_init_step_i2c(climate_node_init_context_t *ctx,
                                     climate_node_init_step_result_t *result);

// Шаг 4: Sensors (SHT3x, CCS811)
esp_err_t climate_node_init_step_sensors(climate_node_init_context_t *ctx,
                                         climate_node_init_step_result_t *result);

// Шаг 5: OLED UI
esp_err_t climate_node_init_step_oled(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result);

// Шаг 6: Actuators (Relay, PWM)
esp_err_t climate_node_init_step_actuators(climate_node_init_context_t *ctx,
                                           climate_node_init_step_result_t *result);

// Шаг 7: MQTT Manager
esp_err_t climate_node_init_step_mqtt(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result);

// Шаг 8: Finalization
esp_err_t climate_node_init_step_finalize(climate_node_init_context_t *ctx,
                                          climate_node_init_step_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // CLIMATE_NODE_INIT_STEPS_H

