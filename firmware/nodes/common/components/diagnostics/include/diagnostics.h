/**
 * @file diagnostics.h
 * @brief Компонент диагностики и сбора метрик
 * 
 * Компонент предоставляет:
 * - Централизованный сбор метрик системы
 * - Публикация диагностики через MQTT
 * - API для запроса диагностики через команды
 * - Метрики: память, uptime, ошибки, MQTT, сенсоры
 */

#ifndef DIAGNOSTICS_H
#define DIAGNOSTICS_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация компонента диагностики
 */
typedef struct {
    uint32_t publish_interval_ms;  ///< Интервал публикации метрик (по умолчанию 60000)
    bool enable_auto_publish;      ///< Автоматическая публикация метрик (по умолчанию true)
    bool enable_metrics;           ///< Включить сбор метрик (по умолчанию true)
} diagnostics_config_t;

/**
 * @brief Метрики использования памяти
 */
typedef struct {
    size_t free_heap;              ///< Свободная память heap (байты)
    size_t min_free_heap;          ///< Минимальная свободная память heap (байты)
    size_t largest_free_block;     ///< Самый большой свободный блок (байты)
    uint32_t heap_allocations;     ///< Количество выделений памяти
    uint32_t heap_frees;           ///< Количество освобождений памяти
} diagnostics_memory_metrics_t;

/**
 * @brief Метрики задач FreeRTOS
 */
typedef struct {
    char task_name[16];            ///< Имя задачи
    uint32_t stack_high_water_mark; ///< Минимальный свободный стек (байты)
    uint32_t runtime_ms;           ///< Время выполнения задачи (миллисекунды)
    uint32_t core_id;              ///< ID ядра (0 или 1)
} diagnostics_task_metrics_t;

/**
 * @brief Метрики MQTT
 */
typedef struct {
    uint32_t messages_sent;        ///< Количество отправленных сообщений
    uint32_t messages_received;    ///< Количество полученных сообщений
    uint32_t publish_errors;       ///< Количество ошибок публикации
    uint32_t subscribe_errors;     ///< Количество ошибок подписки
    bool connected;                ///< Статус подключения
    uint32_t reconnect_count;     ///< Количество переподключений
} diagnostics_mqtt_metrics_t;

/**
 * @brief Метрики сенсоров
 */
typedef struct {
    char sensor_name[16];          ///< Имя сенсора
    uint32_t read_count;           ///< Количество успешных чтений
    uint32_t error_count;          ///< Количество ошибок чтения
    uint32_t last_read_time_ms;    ///< Время последнего чтения (миллисекунды)
    bool initialized;              ///< Статус инициализации
} diagnostics_sensor_metrics_t;

/**
 * @brief Метрики ошибок
 */
typedef struct {
    uint32_t warning_count;       ///< Количество предупреждений
    uint32_t error_count;          ///< Количество ошибок
    uint32_t critical_count;       ///< Количество критических ошибок
    uint32_t total_count;          ///< Общее количество ошибок
} diagnostics_error_metrics_t;

/**
 * @brief Полная диагностическая информация
 */
typedef struct {
    // Системные метрики
    uint64_t uptime_seconds;        ///< Время работы в секундах
    diagnostics_memory_metrics_t memory; ///< Метрики памяти
    
    // Метрики ошибок
    diagnostics_error_metrics_t errors; ///< Метрики ошибок
    
    // Метрики MQTT
    diagnostics_mqtt_metrics_t mqtt; ///< Метрики MQTT
    
    // Метрики задач (массив, максимум 16 задач)
    diagnostics_task_metrics_t tasks[16];
    uint32_t task_count;           ///< Количество задач
    
    // Метрики сенсоров (массив, максимум 8 сенсоров)
    diagnostics_sensor_metrics_t sensors[8];
    uint32_t sensor_count;          ///< Количество сенсоров
    
    // Дополнительные метрики
    int8_t wifi_rssi;              ///< RSSI Wi-Fi
    bool wifi_connected;            ///< Статус подключения Wi-Fi
    bool safe_mode;                ///< Режим безопасной работы
} diagnostics_snapshot_t;

/**
 * @brief Инициализация компонента диагностики
 * 
 * @param config Конфигурация (может быть NULL для значений по умолчанию)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t diagnostics_init(const diagnostics_config_t *config);

/**
 * @brief Деинициализация компонента диагностики
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t diagnostics_deinit(void);

/**
 * @brief Получить снимок диагностической информации
 * 
 * @param snapshot Указатель на структуру для заполнения
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t diagnostics_get_snapshot(diagnostics_snapshot_t *snapshot);

/**
 * @brief Публиковать диагностику через MQTT
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t diagnostics_publish(void);

/**
 * @brief Обновить метрики MQTT (вызывается из mqtt_manager)
 * 
 * @param message_sent true если сообщение отправлено
 * @param message_received true если сообщение получено
 * @param error true если произошла ошибка
 */
void diagnostics_update_mqtt_metrics(bool message_sent, bool message_received, bool error);

/**
 * @brief Обновить метрики сенсора
 * 
 * @param sensor_name Имя сенсора
 * @param read_success true если чтение успешно
 */
void diagnostics_update_sensor_metrics(const char *sensor_name, bool read_success);

/**
 * @brief Проверить, инициализирован ли компонент
 * 
 * @return true если компонент инициализирован
 */
bool diagnostics_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // DIAGNOSTICS_H

