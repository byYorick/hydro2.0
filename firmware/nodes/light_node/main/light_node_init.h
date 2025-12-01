/**
 * @file light_node_init.h
 * @brief Component initialization, setup mode and callbacks for light_node
 */

#ifndef LIGHT_NODE_INIT_H
#define LIGHT_NODE_INIT_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize all light_node components
 * @return ESP_OK on success
 */
esp_err_t light_node_init_components(void);

/**
 * @brief Run setup mode (WiFi provisioning)
 */
void light_node_run_setup_mode(void);

/**
 * @brief MQTT connection callback
 */
void light_node_mqtt_connection_cb(bool connected, void *user_ctx);

/**
 * @brief WiFi connection callback
 */
void light_node_wifi_connection_cb(bool connected, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_INIT_H

