/**
 * @file ph_node_init.h
 * @brief Component initialization for ph_node
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

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_INIT_H

