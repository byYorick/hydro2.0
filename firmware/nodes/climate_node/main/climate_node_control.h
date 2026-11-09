/**
 * Исполнение set_position для фрамуг.
 * Потеря связи и E-STOP останавливают приводы. Автономного термостата нет.
 */
#ifndef CLIMATE_NODE_CONTROL_H
#define CLIMATE_NODE_CONTROL_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t climate_node_control_init(void);
void climate_node_control_apply_now(void);
bool climate_node_control_estop_latched(void);

#ifdef __cplusplus
}
#endif

#endif /* CLIMATE_NODE_CONTROL_H */
