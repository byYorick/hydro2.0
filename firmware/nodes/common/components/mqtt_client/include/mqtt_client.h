/**
 * @file mqtt_client.h
 * @brief Алиас для mqtt_manager.h для обратной совместимости
 * 
 * Этот файл предоставляет алиасы функций mqtt_manager_* как mqtt_client_*
 * для совместимости с существующим кодом узлов.
 * 
 * @note Рекомендуется использовать mqtt_manager.h напрямую в новом коде
 */

#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include "mqtt_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

// Алиасы типов
typedef mqtt_manager_config_t mqtt_client_config_t;
typedef mqtt_node_info_t mqtt_client_node_info_t;
typedef mqtt_config_callback_t mqtt_client_config_callback_t;
typedef mqtt_command_callback_t mqtt_client_command_callback_t;
typedef mqtt_connection_callback_t mqtt_client_connection_callback_t;

// Алиасы функций для обратной совместимости
#define mqtt_client_init mqtt_manager_init
#define mqtt_client_start mqtt_manager_start
#define mqtt_client_stop mqtt_manager_stop
#define mqtt_client_deinit mqtt_manager_deinit
#define mqtt_client_register_config_cb mqtt_manager_register_config_cb
#define mqtt_client_register_command_cb mqtt_manager_register_command_cb
#define mqtt_client_register_connection_cb mqtt_manager_register_connection_cb
#define mqtt_client_publish_telemetry mqtt_manager_publish_telemetry
#define mqtt_client_publish_status mqtt_manager_publish_status
#define mqtt_client_publish_heartbeat mqtt_manager_publish_heartbeat
#define mqtt_client_publish_command_response mqtt_manager_publish_command_response
#define mqtt_client_publish_config_report mqtt_manager_publish_config_report
#define mqtt_client_is_connected mqtt_manager_is_connected
#define mqtt_client_reconnect mqtt_manager_reconnect

#ifdef __cplusplus
}
#endif

#endif // MQTT_CLIENT_H
