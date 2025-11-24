/**
 * @file node_telemetry_engine.h
 * @brief Движок публикации телеметрии для фреймворка нод
 * 
 * Унифицированная публикация телеметрии:
 * - Автоматическое формирование топика по NodeConfig
 * - Батчинг телеметрии
 * - Единый формат JSON
 */

#ifndef NODE_TELEMETRY_ENGINE_H
#define NODE_TELEMETRY_ENGINE_H

#include "esp_err.h"
#include "cJSON.h"
#include "node_framework.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Публикация телеметрии сенсора
 * 
 * @param channel Имя канала
 * @param metric_type Тип метрики
 * @param value Значение
 * @param unit Единица измерения (опционально, может быть NULL)
 * @param raw Сырое значение сенсора (опционально, 0 если не используется)
 * @param stub Флаг симулированного значения (опционально, false если не используется)
 * @param stable Флаг стабильности (опционально, true если не используется)
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_publish_sensor(
    const char *channel,
    metric_type_t metric_type,
    float value,
    const char *unit,
    int32_t raw,
    bool stub,
    bool stable
);

/**
 * @brief Публикация телеметрии актуатора
 * 
 * @param channel Имя канала
 * @param metric_type Тип метрики
 * @param state Состояние (например, "ON", "OFF", "RUNNING")
 * @param value Числовое значение (опционально, 0 если не используется)
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_publish_actuator(
    const char *channel,
    metric_type_t metric_type,
    const char *state,
    float value
);

/**
 * @brief Публикация телеметрии с полным контролем
 * 
 * @param channel Имя канала
 * @param metric_type_str Строковое представление типа метрики (например, "PH", "EC")
 * @param value Значение
 * @param raw Сырое значение (опционально)
 * @param stub Флаг симулированного значения (опционально)
 * @param stable Флаг стабильности (опционально)
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_publish_custom(
    const char *channel,
    const char *metric_type_str,
    float value,
    int32_t raw,
    bool stub,
    bool stable
);

/**
 * @brief Принудительная отправка батча телеметрии
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_flush(void);

/**
 * @brief Установка интервала батчинга телеметрии
 * 
 * @param interval_ms Интервал в миллисекундах
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_set_batch_interval(uint32_t interval_ms);

/**
 * @brief Установка размера батча телеметрии
 * 
 * @param batch_size Размер батча (количество сообщений)
 * @return ESP_OK при успехе
 */
esp_err_t node_telemetry_set_batch_size(uint32_t batch_size);

#ifdef __cplusplus
}
#endif

#endif // NODE_TELEMETRY_ENGINE_H

