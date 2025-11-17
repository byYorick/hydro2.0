/**
 * @file ph_node_telemetry.h
 * @brief Telemetry publishing for ph_node
 */

#ifndef PH_NODE_TELEMETRY_H
#define PH_NODE_TELEMETRY_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Publish pH telemetry with real values from Trema pH sensor
 */
void ph_node_publish_telemetry(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_TELEMETRY_H

