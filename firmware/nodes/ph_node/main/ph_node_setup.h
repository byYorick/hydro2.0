/**
 * @file ph_node_setup.h
 * @brief Setup portal logic for ph_node
 */

#ifndef PH_NODE_SETUP_H
#define PH_NODE_SETUP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Run setup mode (AP + web portal)
 * This function blocks until WiFi credentials are received or timeout
 */
void ph_node_run_setup_mode(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_SETUP_H

