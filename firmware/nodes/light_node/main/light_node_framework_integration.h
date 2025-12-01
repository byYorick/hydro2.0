/**
 * @file light_node_framework_integration.h
 * @brief Интеграция light_node с node_framework
 */

#ifndef LIGHT_NODE_FRAMEWORK_INTEGRATION_H
#define LIGHT_NODE_FRAMEWORK_INTEGRATION_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t light_node_framework_init_integration(void);
void light_node_framework_register_mqtt_handlers(void);
esp_err_t light_node_publish_telemetry_callback(void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_FRAMEWORK_INTEGRATION_H

