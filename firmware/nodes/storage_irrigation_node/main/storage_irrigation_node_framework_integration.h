/**
 * @file storage_irrigation_node_framework_integration.h
 * @brief Интеграция storage_irrigation_node с node_framework
 * 
 * Этот файл связывает storage_irrigation_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#ifndef STORAGE_IRRIGATION_NODE_FRAMEWORK_INTEGRATION_H
#define STORAGE_IRRIGATION_NODE_FRAMEWORK_INTEGRATION_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация интеграции storage_irrigation_node с node_framework
 * 
 * Регистрирует обработчики команд и настраивает callbacks для:
 * - Обработки NodeConfig
 * - Обработки команд (`set_relay`, `state`, `run_pump`)
 * - Публикации телеметрии
 * 
 * @return ESP_OK при успехе
 */
esp_err_t storage_irrigation_node_framework_init_integration(void);

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 * 
 * Устанавливает callbacks для mqtt_manager для обработки config и command сообщений
 */
void storage_irrigation_node_framework_register_mqtt_handlers(void);

/**
 * @brief Callback для публикации телеметрии pump
 * 
 * Используется в storage_irrigation_node_tasks.c для периодической публикации телеметрии
 * 
 * @param user_ctx Пользовательский контекст (не используется)
 * @return ESP_OK при успехе
 */
esp_err_t storage_irrigation_node_publish_telemetry_callback(void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // STORAGE_IRRIGATION_NODE_FRAMEWORK_INTEGRATION_H
