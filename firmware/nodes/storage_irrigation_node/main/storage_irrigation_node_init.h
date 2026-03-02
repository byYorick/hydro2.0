/**
 * @file storage_irrigation_node_init.h
 * @brief Component initialization, setup mode and callbacks for storage_irrigation_node
 */

#ifndef STORAGE_IRRIGATION_NODE_INIT_H
#define STORAGE_IRRIGATION_NODE_INIT_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize all storage_irrigation_node components
 * @return ESP_OK on success
 */
esp_err_t storage_irrigation_node_init_components(void);

/**
 * @brief Run setup mode (WiFi provisioning)
 */
void storage_irrigation_node_run_setup_mode(void);

/**
 * @brief MQTT connection callback
 */
void storage_irrigation_node_mqtt_connection_cb(bool connected, void *user_ctx);

/**
 * @brief WiFi connection callback
 */
void storage_irrigation_node_wifi_connection_cb(bool connected, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // STORAGE_IRRIGATION_NODE_INIT_H

