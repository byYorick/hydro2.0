/**
 * @file ph_sensor.c
 * @brief Реализация драйвера pH-сенсора
 * 
 * Компонент реализует драйвер для pH-датчика:
 * - Чтение ADC значения (аналоговый pH-датчик)
 * - Калибровка (2-3 точки)
 * - Температурная компенсация
 * - Медианный фильтр
 * - Проверка диапазона значений
 * 
 * Стандарты кодирования:
 * - Именование функций: ph_sensor_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "ph_sensor.h"
#include "i2c_bus.h"
#include "config_storage.h"
#include "esp_log.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <stdbool.h>
#include "cJSON.h"

static const char *TAG = "ph_sensor";

// Внутренние структуры
static struct {
    bool initialized;
    ph_sensor_config_t config;
    ph_calibration_point_t *cal_points;
    size_t cal_points_count;
    ph_calibration_method_t cal_method;
    
    // Медианный фильтр
    float *filter_buffer;
    size_t filter_size;
    size_t filter_index;
    bool filter_ready;
    
    // ADC калибровка (для аналогового датчика)
    adc_oneshot_unit_handle_t adc_handle;
    adc_channel_t adc_channel;
    adc_atten_t adc_atten;
} s_ph_sensor = {0};

// Константы
#define PH_SENSOR_DEFAULT_MIN 4.0f
#define PH_SENSOR_DEFAULT_MAX 10.0f
#define PH_SENSOR_FILTER_SIZE 5
#define PH_SENSOR_ADC_VREF 3300  // 3.3V в милливольтах
#define PH_SENSOR_ADC_RESOLUTION 4095  // 12-bit ADC

// Внутренние функции
static float ph_sensor_apply_calibration(float raw_value);
static float ph_sensor_apply_temp_compensation(float ph_value, float temperature);
static float ph_sensor_median_filter(float value);
static esp_err_t ph_sensor_read_analog(float *voltage);
static esp_err_t ph_sensor_read_i2c(float *raw_value);
static int compare_float(const void *a, const void *b);

/**
 * @brief Применение калибровки к сырому значению
 */
static float ph_sensor_apply_calibration(float raw_value) {
    if (s_ph_sensor.cal_points_count < 2) {
        // Нет калибровки, возвращаем сырое значение
        return raw_value;
    }
    
    // Линейная интерполяция (для MVP)
    if (s_ph_sensor.cal_method == PH_CALIBRATION_LINEAR) {
        // Поиск двух ближайших точек
        for (size_t i = 0; i < s_ph_sensor.cal_points_count - 1; i++) {
            float v1 = s_ph_sensor.cal_points[i].voltage;
            float v2 = s_ph_sensor.cal_points[i + 1].voltage;
            
            if (raw_value >= v1 && raw_value <= v2) {
                // Линейная интерполяция
                float ph1 = s_ph_sensor.cal_points[i].ph_value;
                float ph2 = s_ph_sensor.cal_points[i + 1].ph_value;
                
                float ratio = (raw_value - v1) / (v2 - v1);
                return ph1 + (ph2 - ph1) * ratio;
            }
        }
        
        // Экстраполяция за пределами калибровки
        if (raw_value < s_ph_sensor.cal_points[0].voltage) {
            float v1 = s_ph_sensor.cal_points[0].voltage;
            float v2 = s_ph_sensor.cal_points[1].voltage;
            float ph1 = s_ph_sensor.cal_points[0].ph_value;
            float ph2 = s_ph_sensor.cal_points[1].ph_value;
            float slope = (ph2 - ph1) / (v2 - v1);
            return ph1 + (raw_value - v1) * slope;
        } else {
            size_t last = s_ph_sensor.cal_points_count - 1;
            float v1 = s_ph_sensor.cal_points[last - 1].voltage;
            float v2 = s_ph_sensor.cal_points[last].voltage;
            float ph1 = s_ph_sensor.cal_points[last - 1].ph_value;
            float ph2 = s_ph_sensor.cal_points[last].ph_value;
            float slope = (ph2 - ph1) / (v2 - v1);
            return ph2 + (raw_value - v2) * slope;
        }
    }
    
    // По умолчанию возвращаем сырое значение
    return raw_value;
}

/**
 * @brief Применение температурной компенсации
 */
static float ph_sensor_apply_temp_compensation(float ph_value, float temperature) {
    if (!s_ph_sensor.config.enable_temp_compensation || isnan(temperature)) {
        return ph_value;
    }
    
    // Простая линейная компенсация
    // pH изменяется примерно на 0.03 единицы на градус
    float temp_correction = (temperature - 25.0f) * s_ph_sensor.config.temp_coefficient;
    return ph_value + temp_correction;
}

/**
 * @brief Медианный фильтр
 */
static float ph_sensor_median_filter(float value) {
    if (s_ph_sensor.filter_buffer == NULL) {
        return value;
    }
    
    // Добавление значения в буфер
    s_ph_sensor.filter_buffer[s_ph_sensor.filter_index] = value;
    s_ph_sensor.filter_index = (s_ph_sensor.filter_index + 1) % s_ph_sensor.filter_size;
    
    if (!s_ph_sensor.filter_ready && s_ph_sensor.filter_index == 0) {
        s_ph_sensor.filter_ready = true;
    }
    
    if (!s_ph_sensor.filter_ready) {
        return value;
    }
    
    // Копирование и сортировка
    float *sorted = malloc(s_ph_sensor.filter_size * sizeof(float));
    if (sorted == NULL) {
        return value;
    }
    
    memcpy(sorted, s_ph_sensor.filter_buffer, s_ph_sensor.filter_size * sizeof(float));
    qsort(sorted, s_ph_sensor.filter_size, sizeof(float), compare_float);
    
    // Медиана
    float median = sorted[s_ph_sensor.filter_size / 2];
    free(sorted);
    
    return median;
}

/**
 * @brief Сравнение float для qsort
 */
static int compare_float(const void *a, const void *b) {
    float fa = *(const float*)a;
    float fb = *(const float*)b;
    return (fa > fb) - (fa < fb);
}

/**
 * @brief Чтение аналогового значения
 */
static esp_err_t ph_sensor_read_analog(float *voltage) {
    if (voltage == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Чтение ADC (ESP-IDF 5.x API)
    int adc_value = 0;
    esp_err_t err = adc_oneshot_read(s_ph_sensor.adc_handle, s_ph_sensor.adc_channel, &adc_value);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read ADC: %s", esp_err_to_name(err));
        return err;
    }
    
    // Преобразование в напряжение (упрощенное, без калибровки)
    // В реальности нужно использовать esp_adc_cal для точного преобразования
    // Для MVP используем линейное преобразование
    *voltage = (float)adc_value * 3.3f / 4095.0f;  // 12-bit, 3.3V reference
    
    return ESP_OK;
}

/**
 * @brief Чтение I²C значения
 */
static esp_err_t ph_sensor_read_i2c(float *raw_value) {
    if (raw_value == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    // Упрощенная реализация - чтение 2 байт
    uint8_t data[2];
    esp_err_t err = i2c_bus_read(s_ph_sensor.config.i2c_address, NULL, 0, data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read from I²C device: %s", esp_err_to_name(err));
        return err;
    }
    
    // Преобразование в float (зависит от формата датчика)
    uint16_t raw = (data[0] << 8) | data[1];
    *raw_value = raw / 100.0f;  // Пример: датчик возвращает значение * 100
    
    return ESP_OK;
}

// Публичные функции

esp_err_t ph_sensor_init(const ph_sensor_config_t *config) {
    if (config == NULL) {
        ESP_LOGE(TAG, "Invalid config: NULL");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (s_ph_sensor.initialized) {
        ESP_LOGW(TAG, "pH sensor already initialized");
        return ESP_OK;
    }
    
    // Сохранение конфигурации
    memcpy(&s_ph_sensor.config, config, sizeof(ph_sensor_config_t));
    
    // Инициализация в зависимости от типа
    if (config->type == PH_SENSOR_TYPE_ANALOG) {
        // Инициализация ADC (ESP-IDF 5.x API)
        adc_oneshot_unit_init_cfg_t init_config = {
            .unit_id = ADC_UNIT_1,
        };
        esp_err_t err = adc_oneshot_new_unit(&init_config, &s_ph_sensor.adc_handle);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize ADC unit: %s", esp_err_to_name(err));
            return err;
        }
        
        s_ph_sensor.adc_channel = (adc_channel_t)config->adc_channel;
        s_ph_sensor.adc_atten = ADC_ATTEN_DB_11;
        
        adc_oneshot_chan_cfg_t channel_config = {
            .bitwidth = ADC_BITWIDTH_12,
            .atten = s_ph_sensor.adc_atten,
        };
        err = adc_oneshot_config_channel(s_ph_sensor.adc_handle, s_ph_sensor.adc_channel, &channel_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure ADC channel: %s", esp_err_to_name(err));
            adc_oneshot_del_unit(s_ph_sensor.adc_handle);
            return err;
        }
        
        ESP_LOGI(TAG, "ADC initialized for analog pH sensor");
    }
    
    // Инициализация калибровки
    if (config->cal_points != NULL && config->cal_points_count > 0) {
        s_ph_sensor.cal_points = malloc(config->cal_points_count * sizeof(ph_calibration_point_t));
        if (s_ph_sensor.cal_points == NULL) {
            ESP_LOGE(TAG, "Failed to allocate memory for calibration points");
            return ESP_ERR_NO_MEM;
        }
        memcpy(s_ph_sensor.cal_points, config->cal_points, 
               config->cal_points_count * sizeof(ph_calibration_point_t));
        s_ph_sensor.cal_points_count = config->cal_points_count;
        s_ph_sensor.cal_method = config->cal_method;
    } else {
        s_ph_sensor.cal_points = NULL;
        s_ph_sensor.cal_points_count = 0;
    }
    
    // Инициализация медианного фильтра
    s_ph_sensor.filter_size = PH_SENSOR_FILTER_SIZE;
    s_ph_sensor.filter_buffer = malloc(s_ph_sensor.filter_size * sizeof(float));
    if (s_ph_sensor.filter_buffer == NULL) {
        ESP_LOGE(TAG, "Failed to allocate memory for filter buffer");
        if (s_ph_sensor.cal_points != NULL) {
            free(s_ph_sensor.cal_points);
        }
        return ESP_ERR_NO_MEM;
    }
    memset(s_ph_sensor.filter_buffer, 0, s_ph_sensor.filter_size * sizeof(float));
    s_ph_sensor.filter_index = 0;
    s_ph_sensor.filter_ready = false;
    
    // Установка значений по умолчанию
    if (s_ph_sensor.config.min_value == 0.0f) {
        s_ph_sensor.config.min_value = PH_SENSOR_DEFAULT_MIN;
    }
    if (s_ph_sensor.config.max_value == 0.0f) {
        s_ph_sensor.config.max_value = PH_SENSOR_DEFAULT_MAX;
    }
    
    s_ph_sensor.initialized = true;
    ESP_LOGI(TAG, "pH sensor initialized (type=%d, cal_points=%zu)", 
            config->type, s_ph_sensor.cal_points_count);
    
    return ESP_OK;
}

esp_err_t ph_sensor_deinit(void) {
    if (!s_ph_sensor.initialized) {
        return ESP_OK;
    }
    
    // Деинициализация ADC
    if (s_ph_sensor.config.type == PH_SENSOR_TYPE_ANALOG && s_ph_sensor.adc_handle != NULL) {
        adc_oneshot_del_unit(s_ph_sensor.adc_handle);
        s_ph_sensor.adc_handle = NULL;
    }
    
    if (s_ph_sensor.cal_points != NULL) {
        free(s_ph_sensor.cal_points);
        s_ph_sensor.cal_points = NULL;
    }
    
    if (s_ph_sensor.filter_buffer != NULL) {
        free(s_ph_sensor.filter_buffer);
        s_ph_sensor.filter_buffer = NULL;
    }
    
    s_ph_sensor.initialized = false;
    ESP_LOGI(TAG, "pH sensor deinitialized");
    return ESP_OK;
}

esp_err_t ph_sensor_read(ph_sensor_reading_t *reading, float temperature) {
    if (!s_ph_sensor.initialized) {
        ESP_LOGE(TAG, "pH sensor not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (reading == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    memset(reading, 0, sizeof(ph_sensor_reading_t));
    
    // Чтение сырого значения
    float raw_value = 0.0f;
    float voltage = 0.0f;
    esp_err_t err = ESP_OK;
    
    if (s_ph_sensor.config.type == PH_SENSOR_TYPE_ANALOG) {
        err = ph_sensor_read_analog(&voltage);
        if (err != ESP_OK) {
            reading->valid = false;
            return err;
        }
        raw_value = voltage;
    } else {
        err = ph_sensor_read_i2c(&raw_value);
        if (err != ESP_OK) {
            reading->valid = false;
            return err;
        }
    }
    
    reading->raw_value = raw_value;
    reading->voltage = voltage;
    
    // Применение калибровки
    float ph_value = ph_sensor_apply_calibration(raw_value);
    
    // Применение температурной компенсации
    ph_value = ph_sensor_apply_temp_compensation(ph_value, temperature);
    
    // Медианный фильтр
    ph_value = ph_sensor_median_filter(ph_value);
    
    reading->ph_value = ph_value;
    reading->valid = true;
    
    // Проверка диапазона
    reading->in_range = (ph_value >= s_ph_sensor.config.min_value && 
                         ph_value <= s_ph_sensor.config.max_value);
    
    // Проверка предупреждений
    reading->warning = (ph_value < s_ph_sensor.config.warning_low || 
                       ph_value > s_ph_sensor.config.warning_high);
    
    return ESP_OK;
}

esp_err_t ph_sensor_calibrate(const ph_calibration_point_t *points, size_t points_count,
                              ph_calibration_method_t method) {
    if (!s_ph_sensor.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (points == NULL || points_count < 2) {
        ESP_LOGE(TAG, "Invalid calibration points");
        return ESP_ERR_INVALID_ARG;
    }
    
    // Освобождение старых точек
    if (s_ph_sensor.cal_points != NULL) {
        free(s_ph_sensor.cal_points);
    }
    
    // Выделение памяти для новых точек
    s_ph_sensor.cal_points = malloc(points_count * sizeof(ph_calibration_point_t));
    if (s_ph_sensor.cal_points == NULL) {
        ESP_LOGE(TAG, "Failed to allocate memory for calibration points");
        return ESP_ERR_NO_MEM;
    }
    
    memcpy(s_ph_sensor.cal_points, points, points_count * sizeof(ph_calibration_point_t));
    s_ph_sensor.cal_points_count = points_count;
    s_ph_sensor.cal_method = method;
    
    ESP_LOGI(TAG, "pH sensor calibrated with %zu points, method=%d", points_count, method);
    return ESP_OK;
}

esp_err_t ph_sensor_get_calibration(ph_calibration_point_t *points, size_t max_points,
                                   size_t *points_count) {
    if (!s_ph_sensor.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (points == NULL || points_count == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    size_t copy_count = (s_ph_sensor.cal_points_count < max_points) ? 
                        s_ph_sensor.cal_points_count : max_points;
    
    if (s_ph_sensor.cal_points != NULL && copy_count > 0) {
        memcpy(points, s_ph_sensor.cal_points, copy_count * sizeof(ph_calibration_point_t));
    }
    
    *points_count = copy_count;
    return ESP_OK;
}

bool ph_sensor_is_valid(float ph_value) {
    if (!s_ph_sensor.initialized) {
        return false;
    }
    
    return (ph_value >= s_ph_sensor.config.min_value && 
            ph_value <= s_ph_sensor.config.max_value);
}

esp_err_t ph_sensor_init_from_config(const char *channel_id) {
    // Загрузка конфигурации из NodeConfig
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char config_json[4096];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load config from storage");
        return err;
    }
    
    // Парсинг JSON и извлечение конфигурации канала
    // Упрощенная реализация - в реальности нужно парсить channels массив
    // Для MVP используем значения по умолчанию
    ph_sensor_config_t config = {
        .type = PH_SENSOR_TYPE_ANALOG,
        .adc_channel = ADC_CHANNEL_0,
        .cal_points = NULL,
        .cal_points_count = 0,
        .cal_method = PH_CALIBRATION_LINEAR,
        .min_value = PH_SENSOR_DEFAULT_MIN,
        .max_value = PH_SENSOR_DEFAULT_MAX,
        .warning_low = 5.5f,
        .warning_high = 7.5f,
        .enable_temp_compensation = false,
        .temp_coefficient = 0.03f
    };
    
    return ph_sensor_init(&config);
}

