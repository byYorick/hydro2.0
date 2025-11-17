/**
 * @file ph_sensor.h
 * @brief Драйвер pH-сенсора для узлов ESP32
 * 
 * Компонент реализует драйвер для pH-датчика:
 * - Чтение ADC значения (аналоговый pH-датчик)
 * - Калибровка (2-3 точки) согласно NodeConfig
 * - Температурная компенсация (если доступна температура)
 * - Медианный фильтр для сглаживания значений
 * - Проверка диапазона значений (4.0-10.0 pH)
 * - Интеграция с i2c_bus (если используется I²C датчик)
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 */

#ifndef PH_SENSOR_H
#define PH_SENSOR_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Тип pH-датчика
 */
typedef enum {
    PH_SENSOR_TYPE_ANALOG,  ///< Аналоговый датчик (ADC)
    PH_SENSOR_TYPE_I2C      ///< I²C датчик
} ph_sensor_type_t;

/**
 * @brief Точка калибровки
 */
typedef struct {
    float ph_value;    ///< Значение pH
    float voltage;     ///< Напряжение (для аналогового) или raw значение
} ph_calibration_point_t;

/**
 * @brief Метод калибровки
 */
typedef enum {
    PH_CALIBRATION_LINEAR,      ///< Линейная интерполяция
    PH_CALIBRATION_POLYNOMIAL,  ///< Полиномиальная интерполяция
    PH_CALIBRATION_SPLINE       ///< Сплайн-интерполяция
} ph_calibration_method_t;

/**
 * @brief Конфигурация pH-сенсора
 */
typedef struct {
    ph_sensor_type_t type;              ///< Тип датчика
    int adc_channel;                    ///< Канал ADC (для аналогового)
    uint8_t i2c_address;                ///< I²C адрес (для I²C)
    ph_calibration_point_t *cal_points; ///< Точки калибровки
    size_t cal_points_count;            ///< Количество точек калибровки
    ph_calibration_method_t cal_method; ///< Метод калибровки
    float min_value;                    ///< Минимальное значение pH
    float max_value;                    ///< Максимальное значение pH
    float warning_low;                   ///< Нижний порог предупреждения
    float warning_high;                  ///< Верхний порог предупреждения
    bool enable_temp_compensation;       ///< Включить температурную компенсацию
    float temp_coefficient;              ///< Коэффициент температурной компенсации
} ph_sensor_config_t;

/**
 * @brief Результат измерения
 */
typedef struct {
    float ph_value;         ///< Значение pH (откалиброванное)
    float raw_value;        ///< Сырое значение (ADC или I²C)
    float voltage;          ///< Напряжение (для аналогового)
    bool valid;             ///< Валидность измерения
    bool in_range;          ///< В пределах допустимого диапазона
    bool warning;           ///< Предупреждение (выход за пороги)
} ph_sensor_reading_t;

/**
 * @brief Инициализация pH-сенсора
 * 
 * @param config Конфигурация сенсора
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_init(const ph_sensor_config_t *config);

/**
 * @brief Деинициализация pH-сенсора
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_deinit(void);

/**
 * @brief Чтение значения pH
 * 
 * @param reading Указатель на структуру для сохранения результата
 * @param temperature Температура для компенсации (может быть NAN если не используется)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_read(ph_sensor_reading_t *reading, float temperature);

/**
 * @brief Калибровка сенсора
 * 
 * @param points Массив точек калибровки
 * @param points_count Количество точек
 * @param method Метод калибровки
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_calibrate(const ph_calibration_point_t *points, size_t points_count,
                              ph_calibration_method_t method);

/**
 * @brief Получение текущей калибровки
 * 
 * @param points Буфер для сохранения точек калибровки
 * @param max_points Максимальное количество точек
 * @param points_count Указатель для сохранения реального количества точек
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_get_calibration(ph_calibration_point_t *points, size_t max_points,
                                   size_t *points_count);

/**
 * @brief Проверка валидности значения
 * 
 * @param ph_value Значение pH для проверки
 * @return true если значение валидно
 */
bool ph_sensor_is_valid(float ph_value);

/**
 * @brief Инициализация из NodeConfig
 * 
 * Читает конфигурацию из channels секции NodeConfig
 * 
 * @param channel_id ID канала из NodeConfig
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ph_sensor_init_from_config(const char *channel_id);

#ifdef __cplusplus
}
#endif

#endif // PH_SENSOR_H

