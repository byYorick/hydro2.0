/**
 * @file ph_node_tasks.h
 * @brief FreeRTOS tasks for ph_node
 */

#ifndef PH_NODE_TASKS_H
#define PH_NODE_TASKS_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Start FreeRTOS tasks
 */
void ph_node_start_tasks(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_TASKS_H

