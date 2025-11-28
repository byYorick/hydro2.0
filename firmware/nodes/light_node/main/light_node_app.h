/**
 * @file light_node_app.h
 * @brief Заголовочный файл для light_node_app
 */

#ifndef LIGHT_NODE_APP_H
#define LIGHT_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация light_node
 */
void light_node_app_init(void);

/**
 * @brief Запуск FreeRTOS задач
 */
void light_node_start_tasks(void);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_APP_H

