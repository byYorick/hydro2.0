/**
 * @file ph_node_command_handler.h
 * @brief Command message handler for ph_node
 */

#ifndef PH_NODE_COMMAND_HANDLER_H
#define PH_NODE_COMMAND_HANDLER_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Handle MQTT command message
 * @param topic MQTT topic
 * @param channel Channel name
 * @param data JSON command data
 * @param data_len Data length
 * @param user_ctx User context
 */
void ph_node_command_handler(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_COMMAND_HANDLER_H

