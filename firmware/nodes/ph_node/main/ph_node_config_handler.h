/**
 * @file ph_node_config_handler.h
 * @brief Configuration message handler for ph_node
 */

#ifndef PH_NODE_CONFIG_HANDLER_H
#define PH_NODE_CONFIG_HANDLER_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Handle MQTT config message
 * @param topic MQTT topic
 * @param data JSON config data
 * @param data_len Data length
 * @param user_ctx User context
 */
void ph_node_config_handler(const char *topic, const char *data, int data_len, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_CONFIG_HANDLER_H

