/**
 * @file relay_node_init_steps.h
 * @brief Модульная система инициализации relay_node
 * 
 * Разбивает монолитную инициализацию на отдельные шаги,
 * каждый из которых может быть выполнен независимо и повторно.
 */

#ifndef RELAY_NODE_INIT_STEPS_H
#define RELAY_NODE_INIT_STEPS_H

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
} relay_node_init_step_result_t;

/**
 * @brief Контекст инициализации
 */
typedef struct {
    bool show_oled_steps;  // Показывать шаги на OLED
    void *user_ctx;
} relay_node_init_context_t;

// Шаг 1: Config Storage
esp_err_t relay_node_init_step_config_storage(relay_node_init_context_t *ctx, 
                                           relay_node_init_step_result_t *result);

// Шаг 2: Wi-Fi Manager
esp_err_t relay_node_init_step_wifi(relay_node_init_context_t *ctx,
                                  relay_node_init_step_result_t *result);

// Шаг 3: I2C Buses (для OLED, если используется)
esp_err_t relay_node_init_step_i2c(relay_node_init_context_t *ctx,
                                 relay_node_init_step_result_t *result);

// Шаг 4: OLED UI (опционально)
esp_err_t relay_node_init_step_oled(relay_node_init_context_t *ctx,
                                  relay_node_init_step_result_t *result);

// Шаг 5: Relay Driver
esp_err_t relay_node_init_step_relays(relay_node_init_context_t *ctx,
                                   relay_node_init_step_result_t *result);

// Шаг 6: MQTT Manager
esp_err_t relay_node_init_step_mqtt(relay_node_init_context_t *ctx,
                                  relay_node_init_step_result_t *result);

// Шаг 7: Finalization
esp_err_t relay_node_init_step_finalize(relay_node_init_context_t *ctx,
                                      relay_node_init_step_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // RELAY_NODE_INIT_STEPS_H

