/**
 * @file ec_node_app.h
 * @brief Заголовочный файл для ec_node_app
 */

#ifndef EC_NODE_APP_H
#define EC_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация ec_node
 */
void ec_node_app_init(void);

/**
 * @brief Пример публикации телеметрии EC
 */
void ec_node_publish_telemetry_example(void);

/**
 * @brief Запуск FreeRTOS задач
 */
void ec_node_start_tasks(void);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_APP_H

