/**
 * @file ph_node_app.h
 * @brief Заголовочный файл для ph_node_app
 */

#ifndef PH_NODE_APP_H
#define PH_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация ph_node
 */
void ph_node_app_init(void);

/**
 * @brief Пример публикации телеметрии pH
 */
void ph_node_publish_telemetry_example(void);

/**
 * @brief Запуск FreeRTOS задач
 */
void ph_node_start_tasks(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_APP_H

