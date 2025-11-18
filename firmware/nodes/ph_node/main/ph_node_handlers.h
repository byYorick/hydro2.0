/**
 * @file ph_node_handlers.h
 * @brief MQTT message handlers for ph_node
 * 
 * Объединяет обработчики:
 * - Config messages (NodeConfig)
 * - Command messages (команды управления насосами и другими каналами)
 */

#ifndef PH_NODE_HANDLERS_H
#define PH_NODE_HANDLERS_H

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

#endif // PH_NODE_HANDLERS_H


