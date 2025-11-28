/**
 * @file ec_node_init_steps.h
 * @brief Модульная система инициализации ec_node
 * 
 * Разбивает монолитную инициализацию на отдельные шаги,
 * каждый из которых может быть выполнен независимо и повторно.
 */

#ifndef EC_NODE_INIT_STEPS_H
#define EC_NODE_INIT_STEPS_H

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
} ec_node_init_step_result_t;

/**
 * @brief Контекст инициализации
 */
typedef struct {
    bool show_oled_steps;  // Показывать шаги на OLED
    void *user_ctx;
} ec_node_init_context_t;

// Шаг 1: Config Storage
esp_err_t ec_node_init_step_config_storage(ec_node_init_context_t *ctx, 
                                           ec_node_init_step_result_t *result);

// Шаг 2: Wi-Fi Manager
esp_err_t ec_node_init_step_wifi(ec_node_init_context_t *ctx,
                                  ec_node_init_step_result_t *result);

// Шаг 3: I2C Buses
esp_err_t ec_node_init_step_i2c(ec_node_init_context_t *ctx,
                                 ec_node_init_step_result_t *result);

// Шаг 4: EC Sensor
esp_err_t ec_node_init_step_ec_sensor(ec_node_init_context_t *ctx,
                                      ec_node_init_step_result_t *result);

// Шаг 5: OLED UI
esp_err_t ec_node_init_step_oled(ec_node_init_context_t *ctx,
                                  ec_node_init_step_result_t *result);

// Шаг 6: Pump Driver
esp_err_t ec_node_init_step_pumps(ec_node_init_context_t *ctx,
                                   ec_node_init_step_result_t *result);

// Шаг 7: MQTT Manager
esp_err_t ec_node_init_step_mqtt(ec_node_init_context_t *ctx,
                                  ec_node_init_step_result_t *result);

// Шаг 8: Finalization
esp_err_t ec_node_init_step_finalize(ec_node_init_context_t *ctx,
                                      ec_node_init_step_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_INIT_STEPS_H

