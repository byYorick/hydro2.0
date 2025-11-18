/**
 * @file pump_node_app.h
 * @brief Заголовочный файл для pump_node_app
 */

#ifndef PUMP_NODE_APP_H
#define PUMP_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация pump_node
 */
void pump_node_app_init(void);

/**
 * @brief Пример публикации телеметрии
 */
void pump_node_publish_telemetry_example(void);

/**
 * @brief Пример публикации heartbeat
 */
void pump_node_publish_heartbeat_example(void);

/**
 * @brief Обновление интервала опроса тока из NodeConfig
 */
void pump_node_update_current_poll_interval(void);

#ifdef __cplusplus
}
#endif

#endif // PUMP_NODE_APP_H

