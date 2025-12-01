/**
 * @file ec_node_init.h
 * @brief Component initialization, setup mode and callbacks for ec_node
 */

#ifndef EC_NODE_INIT_H
#define EC_NODE_INIT_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize all ec_node components
 * @return ESP_OK on success
 */
esp_err_t ec_node_init_components(void);

/**
 * @brief Run setup mode (WiFi provisioning)
 */
void ec_node_run_setup_mode(void);

/**
 * @brief MQTT connection callback
 */
void ec_node_mqtt_connection_cb(bool connected, void *user_ctx);

/**
 * @brief WiFi connection callback
 */
void ec_node_wifi_connection_cb(bool connected, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_INIT_H

