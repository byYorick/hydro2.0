/**
 * @file pump_control.h
 * @brief Управление насосами pH (pump_acid, pump_base) через GPIO
 * 
 * Реализация управления насосами согласно:
 * - NODE_LOGIC_FULL.md
 * - DEVICE_NODE_PROTOCOL.md
 * - NODE_CHANNELS_REFERENCE.md
 */

#ifndef PUMP_CONTROL_H
#define PUMP_CONTROL_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief ID насосов
 */
typedef enum {
    PUMP_ACID = 0,      // Насос кислоты (pH DOWN)
    PUMP_BASE = 1,      // Насос щелочи (pH UP)
    PUMP_MAX = 2
} pump_id_t;

/**
 * @brief Состояние насоса
 */
typedef enum {
    PUMP_STATE_OFF = 0,
    PUMP_STATE_ON = 1,
    PUMP_STATE_COOLDOWN = 2,
    PUMP_STATE_ERROR = 3
} pump_state_t;

/**
 * @brief Конфигурация насоса
 */
typedef struct {
    int gpio_pin;                    // GPIO пин для управления насосом
    uint32_t max_duration_ms;        // Максимальная длительность работы (мс)
    uint32_t min_off_time_ms;        // Минимальное время простоя (мс)
    float ml_per_second;             // Производительность (мл/сек) для расчета дозы
} pump_config_t;

/**
 * @brief Статистика насоса
 */
typedef struct {
    uint32_t total_runs;             // Количество запусков
    float total_ml;                  // Общий объём (мл)
    uint64_t total_time_ms;          // Общее время работы (мс)
    uint64_t last_run_time;          // Время последнего запуска (мс)
    uint32_t error_count;            // Количество ошибок
} pump_stats_t;

/**
 * @brief Инициализация модуля управления насосами
 * 
 * @param configs Массив конфигураций для каждого насоса (PUMP_MAX элементов)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_init(const pump_config_t *configs);

/**
 * @brief Деинициализация модуля управления насосами
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_deinit(void);

/**
 * @brief Запуск насоса на заданное время
 * 
 * @param pump_id ID насоса
 * @param duration_ms Длительность работы (мс)
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_INVALID_STATE если насос уже работает или в cooldown
 */
esp_err_t pump_control_run(pump_id_t pump_id, uint32_t duration_ms);

/**
 * @brief Запуск насоса с заданной дозой (мл)
 * 
 * @param pump_id ID насоса
 * @param dose_ml Доза в миллилитрах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_dose(pump_id_t pump_id, float dose_ml);

/**
 * @brief Установка состояния насоса (включить/выключить)
 * 
 * @param pump_id ID насоса
 * @param state Состояние (1 = включить, 0 = выключить)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_set_state(pump_id_t pump_id, int state);

/**
 * @brief Остановка насоса
 * 
 * @param pump_id ID насоса
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_stop(pump_id_t pump_id);

/**
 * @brief Аварийная остановка всех насосов
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_emergency_stop(void);

/**
 * @brief Получение текущего состояния насоса
 * 
 * @param pump_id ID насоса
 * @return pump_state_t Текущее состояние
 */
pump_state_t pump_control_get_state(pump_id_t pump_id);

/**
 * @brief Проверка, работает ли насос
 * 
 * @param pump_id ID насоса
 * @return true если насос работает
 */
bool pump_control_is_running(pump_id_t pump_id);

/**
 * @brief Получение статистики насоса
 * 
 * @param pump_id ID насоса
 * @param stats Указатель на структуру для сохранения статистики
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_get_stats(pump_id_t pump_id, pump_stats_t *stats);

/**
 * @brief Сброс статистики насоса
 * 
 * @param pump_id ID насоса
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_reset_stats(pump_id_t pump_id);

/**
 * @brief Обновление конфигурации насоса
 * 
 * @param pump_id ID насоса
 * @param config Новая конфигурация
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_control_update_config(pump_id_t pump_id, const pump_config_t *config);

#ifdef __cplusplus
}
#endif

#endif // PUMP_CONTROL_H

