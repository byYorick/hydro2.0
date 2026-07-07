/**
 * @file node_link_loss_failsafe.h
 * @brief Link-loss fail-safe policy: stop actuators after MQTT disconnect timeout.
 */

#ifndef NODE_LINK_LOSS_FAILSAFE_H
#define NODE_LINK_LOSS_FAILSAFE_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize link-loss failsafe module (called from node_framework_init).
 */
esp_err_t node_link_loss_failsafe_init(void);

/**
 * @brief Reload link_loss_timeout_sec from NodeConfig (after config apply).
 */
void node_link_loss_failsafe_reload_config(void);

/**
 * @brief MQTT connection state hook (called from mqtt_manager).
 *
 * @param connected true on MQTT connect, false on disconnect
 */
void node_link_loss_failsafe_on_mqtt_connected(bool connected);

#ifdef __cplusplus
}
#endif

#endif /* NODE_LINK_LOSS_FAILSAFE_H */
