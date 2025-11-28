/**
 * @file light_node_init_steps.h
 * @brief Модульная система инициализации light_node
 * 
 * Разбивает монолитную инициализацию на отдельные шаги,
 * каждый из которых может быть выполнен независимо и повторно.
 */

#ifndef LIGHT_NODE_INIT_STEPS_H
#define LIGHT_NODE_INIT_STEPS_H

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
} light_node_init_step_result_t;

/**
 * @brief Контекст инициализации
 */
typedef struct {
    bool show_oled_steps;  // Показывать шаги на OLED
    void *user_ctx;
} light_node_init_context_t;

// Шаг 1: Config Storage
esp_err_t light_node_init_step_config_storage(light_node_init_context_t *ctx, 
                                              light_node_init_step_result_t *result);

// Шаг 2: Wi-Fi Manager
esp_err_t light_node_init_step_wifi(light_node_init_context_t *ctx,
                                     light_node_init_step_result_t *result);

// Шаг 3: I2C Bus
esp_err_t light_node_init_step_i2c(light_node_init_context_t *ctx,
                                    light_node_init_step_result_t *result);

// Шаг 4: Light Sensor
esp_err_t light_node_init_step_light_sensor(light_node_init_context_t *ctx,
                                            light_node_init_step_result_t *result);

// Шаг 5: OLED UI
esp_err_t light_node_init_step_oled(light_node_init_context_t *ctx,
                                    light_node_init_step_result_t *result);

// Шаг 6: MQTT Manager
esp_err_t light_node_init_step_mqtt(light_node_init_context_t *ctx,
                                     light_node_init_step_result_t *result);

// Шаг 7: Finalization
esp_err_t light_node_init_step_finalize(light_node_init_context_t *ctx,
                                         light_node_init_step_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_INIT_STEPS_H

