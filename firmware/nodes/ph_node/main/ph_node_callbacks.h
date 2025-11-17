/**
 * @file ph_node_callbacks.h
 * @brief Event callbacks for ph_node
 */

#ifndef PH_NODE_CALLBACKS_H
#define PH_NODE_CALLBACKS_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Handle MQTT connection change
 * @param connected Connection status
 * @param user_ctx User context
 */
void ph_node_mqtt_connection_cb(bool connected, void *user_ctx);

/**
 * @brief Handle Wi-Fi connection change
 * @param connected Connection status
 * @param user_ctx User context
 */
void ph_node_wifi_connection_cb(bool connected, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_CALLBACKS_H

