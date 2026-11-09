/**
 * Локальный термостат climate_node: set_position фрамуг и вытяжка.
 * Работает без MQTT. E-STOP обесточивает всё.
 */
#ifndef CLIMATE_NODE_CONTROL_H
#define CLIMATE_NODE_CONTROL_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t climate_node_control_init(void);
void climate_node_control_set_air(bool valid, float temp_c);
void climate_node_control_apply_now(void);
bool climate_node_control_estop_latched(void);
bool climate_node_control_ventilation_safe(void);

#ifdef __cplusplus
}
#endif

#endif /* CLIMATE_NODE_CONTROL_H */
