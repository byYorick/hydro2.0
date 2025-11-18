/**
 * @file ph_node_init.h
 * @brief Component initialization, setup mode and callbacks for ph_node
 */

#ifndef PH_NODE_INIT_H
#define PH_NODE_INIT_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize all ph_node components
 * @return ESP_OK on success
 */
esp_err_t ph_node_init_components(void);

/**
 * @brief Run setup mode (WiFi provisioning)
 */
void ph_node_run_setup_mode(void);

/**
 * @brief MQTT connection callback
 */
void ph_node_mqtt_connection_cb(bool connected, void *user_ctx);

/**
 * @brief WiFi connection callback
 */
void ph_node_wifi_connection_cb(bool connected, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_INIT_H

