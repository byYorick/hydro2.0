/**
 * @file heartbeat_task.h
 * @brief Компонент для публикации heartbeat во всех нодах
 * 
 * Общая логика heartbeat задачи согласно MQTT_SPEC_FULL.md раздел 9.2
 */

#ifndef HEARTBEAT_TASK_H
#define HEARTBEAT_TASK_H

#include "esp_err.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Запуск задачи heartbeat
 * 
 * Создает FreeRTOS задачу, которая периодически публикует heartbeat
 * 
 * @param interval_ms Интервал публикации в миллисекундах (по умолчанию 15000)
 * @param task_priority Приоритет задачи (по умолчанию 3)
 * @param task_stack_size Размер стека задачи (по умолчанию 3072)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t heartbeat_task_start(uint32_t interval_ms, uint8_t task_priority, uint32_t task_stack_size);

/**
 * @brief Запуск задачи heartbeat с параметрами по умолчанию
 * 
 * Интервал: 15000 мс, приоритет: 3, стек: 3072 байт
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t heartbeat_task_start_default(void);

/**
 * @brief Остановка задачи heartbeat
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t heartbeat_task_stop(void);

#ifdef __cplusplus
}
#endif

#endif // HEARTBEAT_TASK_H

