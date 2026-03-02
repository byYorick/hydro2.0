/**
 * @file storage_irrigation_node_init_steps.h
 * @brief Модульная система инициализации storage_irrigation_node
 * 
 * Разбивает монолитную инициализацию на отдельные шаги,
 * каждый из которых может быть выполнен независимо и повторно.
 */

#ifndef STORAGE_IRRIGATION_NODE_INIT_STEPS_H
#define STORAGE_IRRIGATION_NODE_INIT_STEPS_H

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
} storage_irrigation_node_init_step_result_t;

/**
 * @brief Контекст инициализации
 */
typedef struct {
    bool show_oled_steps;  // Показывать шаги на OLED (для storage_irrigation_node не используется, но для совместимости)
    void *user_ctx;
} storage_irrigation_node_init_context_t;

// Шаг 1: Config Storage
esp_err_t storage_irrigation_node_init_step_config_storage(storage_irrigation_node_init_context_t *ctx, 
                                             storage_irrigation_node_init_step_result_t *result);

// Шаг 2: Wi-Fi Manager
esp_err_t storage_irrigation_node_init_step_wifi(storage_irrigation_node_init_context_t *ctx,
                                   storage_irrigation_node_init_step_result_t *result);

// Шаг 3: I2C Bus (для INA209)
esp_err_t storage_irrigation_node_init_step_i2c(storage_irrigation_node_init_context_t *ctx,
                                   storage_irrigation_node_init_step_result_t *result);

// Шаг 4: Pump Driver
esp_err_t storage_irrigation_node_init_step_pumps(storage_irrigation_node_init_context_t *ctx,
                                    storage_irrigation_node_init_step_result_t *result);

// Шаг 5: OLED UI
esp_err_t storage_irrigation_node_init_step_oled(storage_irrigation_node_init_context_t *ctx,
                                   storage_irrigation_node_init_step_result_t *result);

// Шаг 6: MQTT Manager
esp_err_t storage_irrigation_node_init_step_mqtt(storage_irrigation_node_init_context_t *ctx,
                                    storage_irrigation_node_init_step_result_t *result);

// Шаг 7: Finalization
esp_err_t storage_irrigation_node_init_step_finalize(storage_irrigation_node_init_context_t *ctx,
                                       storage_irrigation_node_init_step_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // STORAGE_IRRIGATION_NODE_INIT_STEPS_H

