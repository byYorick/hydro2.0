/**
 * @file climate_node_app.h
 * @brief Заголовочный файл для climate_node_app
 */

#ifndef CLIMATE_NODE_APP_H
#define CLIMATE_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация climate_node
 */
void climate_node_app_init(void);

/**
 * @brief Пример публикации телеметрии температуры
 */
void climate_node_publish_temperature_example(void);

/**
 * @brief Пример публикации телеметрии влажности
 */
void climate_node_publish_humidity_example(void);

/**
 * @brief Пример публикации телеметрии CO₂
 */
void climate_node_publish_co2_example(void);

/**
 * @brief Пример публикации heartbeat
 */
void climate_node_publish_heartbeat_example(void);

/**
 * @brief Запуск FreeRTOS задач
 */
void climate_node_start_tasks(void);

#ifdef __cplusplus
}
#endif

#endif // CLIMATE_NODE_APP_H

