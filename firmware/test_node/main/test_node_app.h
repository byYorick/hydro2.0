/**
 * @file test_node_app.h
 * @brief Заголовочный файл для тестовой прошивки
 */

#ifndef TEST_NODE_APP_H
#define TEST_NODE_APP_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация тестовой ноды
 * 
 * @return ESP_OK при успехе
 */
esp_err_t test_node_app_init(void);

#ifdef __cplusplus
}
#endif

#endif // TEST_NODE_APP_H

