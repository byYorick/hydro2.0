/**
 * @file connection_status.h
 * @brief Компонент для получения статуса соединений (WiFi, MQTT, RSSI)
 * 
 * Общая логика получения статуса соединений для всех нод
 */

#ifndef CONNECTION_STATUS_H
#define CONNECTION_STATUS_H

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Статус соединений
 */
typedef struct {
    bool wifi_connected;      ///< Подключен ли WiFi
    bool mqtt_connected;       ///< Подключен ли MQTT
    int8_t wifi_rssi;         ///< RSSI WiFi (или -100 если не подключен)
} connection_status_t;

/**
 * @brief Получение текущего статуса соединений
 * 
 * @param status Указатель на структуру для сохранения статуса
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t connection_status_get(connection_status_t *status);

#ifdef __cplusplus
}
#endif

#endif // CONNECTION_STATUS_H

