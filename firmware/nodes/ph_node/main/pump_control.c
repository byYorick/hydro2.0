/**
 * @file pump_control.c
 * @brief Реализация управления насосами pH через GPIO
 */

#include "pump_control.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include <string.h>

static const char *TAG = "pump_control";

// Структура состояния насоса
typedef struct {
    pump_state_t state;
    bool is_running;
    uint64_t start_time_ms;
    uint32_t run_duration_ms;
    uint64_t last_stop_time_ms;
    pump_config_t config;
    pump_stats_t stats;
    TimerHandle_t timer;
} pump_data_t;

static pump_data_t s_pumps[PUMP_MAX];
static bool s_initialized = false;

// Forward declarations
static void pump_timer_callback(TimerHandle_t timer);
static esp_err_t pump_start_internal(pump_id_t pump_id, uint32_t duration_ms);
static esp_err_t pump_stop_internal(pump_id_t pump_id);
static void pump_update_cooldown(pump_id_t pump_id);

/**
 * @brief Инициализация модуля управления насосами
 */
esp_err_t pump_control_init(const pump_config_t *configs) {
    if (s_initialized) {
        ESP_LOGW(TAG, "Pump control already initialized");
        return ESP_OK;
    }

    if (configs == NULL) {
        ESP_LOGE(TAG, "Configs cannot be NULL");
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Initializing pump control (2 pumps for pH)...");

    // Инициализация каждого насоса
    for (int i = 0; i < PUMP_MAX; i++) {
        pump_data_t *pump = &s_pumps[i];
        
        // Копирование конфигурации
        memcpy(&pump->config, &configs[i], sizeof(pump_config_t));
        
        // Инициализация состояния
        pump->state = PUMP_STATE_OFF;
        pump->is_running = false;
        pump->start_time_ms = 0;
        pump->run_duration_ms = 0;
        pump->last_stop_time_ms = 0;
        memset(&pump->stats, 0, sizeof(pump_stats_t));
        
        // Настройка GPIO
        gpio_config_t io_conf = {
            .pin_bit_mask = (1ULL << pump->config.gpio_pin),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        
        esp_err_t ret = gpio_config(&io_conf);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure GPIO %d for pump %d: %s", 
                     pump->config.gpio_pin, i, esp_err_to_name(ret));
            return ret;
        }
        
        // Установка GPIO в LOW (насос выключен)
        gpio_set_level(pump->config.gpio_pin, 0);
        
        // Создание таймера для автоостановки
        char timer_name[16];
        snprintf(timer_name, sizeof(timer_name), "pump%d", i);
        pump->timer = xTimerCreate(timer_name, pdMS_TO_TICKS(1000), 
                                   pdFALSE, (void *)(uintptr_t)i, 
                                   pump_timer_callback);
        
        if (pump->timer == NULL) {
            ESP_LOGE(TAG, "Failed to create timer for pump %d", i);
            return ESP_ERR_NO_MEM;
        }
        
        const char *pump_name = (i == PUMP_ACID) ? "ACID" : "BASE";
        ESP_LOGI(TAG, "Pump %s initialized (GPIO %d, max_duration=%lu ms, min_off=%lu ms)", 
                 pump_name, pump->config.gpio_pin, 
                 (unsigned long)pump->config.max_duration_ms,
                 (unsigned long)pump->config.min_off_time_ms);
    }
    
    s_initialized = true;
    ESP_LOGI(TAG, "Pump control initialized successfully");
    return ESP_OK;
}

/**
 * @brief Деинициализация модуля управления насосами
 */
esp_err_t pump_control_deinit(void) {
    if (!s_initialized) {
        return ESP_OK;
    }
    
    // Остановка всех насосов
    pump_control_emergency_stop();
    
    // Удаление таймеров
    for (int i = 0; i < PUMP_MAX; i++) {
        if (s_pumps[i].timer != NULL) {
            xTimerDelete(s_pumps[i].timer, portMAX_DELAY);
            s_pumps[i].timer = NULL;
        }
    }
    
    s_initialized = false;
    ESP_LOGI(TAG, "Pump control deinitialized");
    return ESP_OK;
}

/**
 * @brief Запуск насоса на заданное время
 */
esp_err_t pump_control_run(pump_id_t pump_id, uint32_t duration_ms) {
    if (pump_id >= PUMP_MAX) {
        ESP_LOGE(TAG, "Invalid pump ID: %d", pump_id);
        return ESP_ERR_INVALID_ARG;
    }
    
    if (duration_ms == 0) {
        ESP_LOGE(TAG, "Duration cannot be zero");
        return ESP_ERR_INVALID_ARG;
    }
    
    pump_data_t *pump = &s_pumps[pump_id];
    
    // Проверка cooldown
    if (pump->state == PUMP_STATE_COOLDOWN) {
        uint64_t now_ms = esp_timer_get_time() / 1000;
        if (now_ms < pump->last_stop_time_ms + pump->config.min_off_time_ms) {
            uint32_t remaining_ms = (pump->last_stop_time_ms + pump->config.min_off_time_ms) - now_ms;
            ESP_LOGW(TAG, "Pump %d in cooldown, %lu ms remaining", pump_id, (unsigned long)remaining_ms);
            return ESP_ERR_INVALID_STATE;
        }
    }
    
    // Проверка, не работает ли уже насос
    if (pump->is_running) {
        ESP_LOGW(TAG, "Pump %d already running", pump_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Ограничение максимальной длительности
    if (duration_ms > pump->config.max_duration_ms) {
        ESP_LOGW(TAG, "Duration %lu ms exceeds max %lu ms, limiting", 
                 (unsigned long)duration_ms, (unsigned long)pump->config.max_duration_ms);
        duration_ms = pump->config.max_duration_ms;
    }
    
    return pump_start_internal(pump_id, duration_ms);
}

/**
 * @brief Запуск насоса с заданной дозой
 */
esp_err_t pump_control_dose(pump_id_t pump_id, float dose_ml) {
    if (pump_id >= PUMP_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (dose_ml <= 0.0f) {
        ESP_LOGE(TAG, "Invalid dose: %.2f ml", dose_ml);
        return ESP_ERR_INVALID_ARG;
    }
    
    pump_data_t *pump = &s_pumps[pump_id];
    
    if (pump->config.ml_per_second <= 0.0f) {
        ESP_LOGE(TAG, "Pump %d not calibrated (ml_per_second = %.2f)", 
                 pump_id, pump->config.ml_per_second);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Расчёт времени работы по калибровке
    uint32_t duration_ms = (uint32_t)((dose_ml / pump->config.ml_per_second) * 1000.0f);
    
    if (duration_ms == 0) {
        duration_ms = 1; // Минимум 1 мс
    }
    
    const char *pump_name = (pump_id == PUMP_ACID) ? "ACID" : "BASE";
    ESP_LOGI(TAG, "Pump %s: dose %.2f ml = %lu ms", 
             pump_name, dose_ml, (unsigned long)duration_ms);
    
    return pump_control_run(pump_id, duration_ms);
}

/**
 * @brief Установка состояния насоса
 */
esp_err_t pump_control_set_state(pump_id_t pump_id, int state) {
    if (pump_id >= PUMP_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (state == 0) {
        return pump_control_stop(pump_id);
    } else if (state == 1) {
        // Включаем на максимальное время (будет остановлен по таймеру или вручную)
        pump_data_t *pump = &s_pumps[pump_id];
        return pump_control_run(pump_id, pump->config.max_duration_ms);
    } else {
        return ESP_ERR_INVALID_ARG;
    }
}

/**
 * @brief Остановка насоса
 */
esp_err_t pump_control_stop(pump_id_t pump_id) {
    if (pump_id >= PUMP_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    return pump_stop_internal(pump_id);
}

/**
 * @brief Аварийная остановка всех насосов
 */
esp_err_t pump_control_emergency_stop(void) {
    ESP_LOGW(TAG, "EMERGENCY STOP - all pumps");
    
    for (int i = 0; i < PUMP_MAX; i++) {
        pump_stop_internal((pump_id_t)i);
    }
    
    return ESP_OK;
}

/**
 * @brief Получение состояния насоса
 */
pump_state_t pump_control_get_state(pump_id_t pump_id) {
    if (pump_id >= PUMP_MAX) {
        return PUMP_STATE_ERROR;
    }
    
    pump_update_cooldown(pump_id);
    return s_pumps[pump_id].state;
}

/**
 * @brief Проверка, работает ли насос
 */
bool pump_control_is_running(pump_id_t pump_id) {
    if (pump_id >= PUMP_MAX) {
        return false;
    }
    
    return s_pumps[pump_id].is_running;
}

/**
 * @brief Получение статистики насоса
 */
esp_err_t pump_control_get_stats(pump_id_t pump_id, pump_stats_t *stats) {
    if (pump_id >= PUMP_MAX || stats == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    memcpy(stats, &s_pumps[pump_id].stats, sizeof(pump_stats_t));
    return ESP_OK;
}

/**
 * @brief Сброс статистики насоса
 */
esp_err_t pump_control_reset_stats(pump_id_t pump_id) {
    if (pump_id >= PUMP_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    memset(&s_pumps[pump_id].stats, 0, sizeof(pump_stats_t));
    ESP_LOGI(TAG, "Pump %d stats reset", pump_id);
    return ESP_OK;
}

/**
 * @brief Обновление конфигурации насоса
 */
esp_err_t pump_control_update_config(pump_id_t pump_id, const pump_config_t *config) {
    if (pump_id >= PUMP_MAX || config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    pump_data_t *pump = &s_pumps[pump_id];
    
    // Если насос работает, не обновляем конфигурацию
    if (pump->is_running) {
        ESP_LOGW(TAG, "Cannot update config while pump %d is running", pump_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    memcpy(&pump->config, config, sizeof(pump_config_t));
    ESP_LOGI(TAG, "Pump %d config updated", pump_id);
    return ESP_OK;
}

// Внутренние функции

/**
 * @brief Внутренняя функция запуска насоса
 */
static esp_err_t pump_start_internal(pump_id_t pump_id, uint32_t duration_ms) {
    pump_data_t *pump = &s_pumps[pump_id];
    
    const char *pump_name = (pump_id == PUMP_ACID) ? "ACID" : "BASE";
    ESP_LOGI(TAG, "Starting pump %s: %lu ms (GPIO %d)", 
             pump_name, (unsigned long)duration_ms, pump->config.gpio_pin);
    
    // Включение GPIO (HIGH = насос включен)
    gpio_set_level(pump->config.gpio_pin, 1);
    
    // Обновление состояния
    pump->state = PUMP_STATE_ON;
    pump->is_running = true;
    pump->start_time_ms = esp_timer_get_time() / 1000; // мс
    pump->run_duration_ms = duration_ms;
    
    // Запуск таймера автоостановки
    xTimerChangePeriod(pump->timer, pdMS_TO_TICKS(duration_ms), 0);
    xTimerStart(pump->timer, 0);
    
    return ESP_OK;
}

/**
 * @brief Внутренняя функция остановки насоса
 */
static esp_err_t pump_stop_internal(pump_id_t pump_id) {
    pump_data_t *pump = &s_pumps[pump_id];
    
    if (!pump->is_running) {
        return ESP_OK; // Уже остановлен
    }
    
    // Выключение GPIO (LOW = насос выключен)
    gpio_set_level(pump->config.gpio_pin, 0);
    
    // Остановка таймера
    xTimerStop(pump->timer, 0);
    
    // Обновление статистики
    uint64_t current_time_ms = esp_timer_get_time() / 1000;
    uint64_t actual_time_ms = current_time_ms - pump->start_time_ms;
    
    pump->stats.total_runs++;
    pump->stats.total_time_ms += actual_time_ms;
    pump->stats.last_run_time = current_time_ms;
    
    // Расчёт объёма
    if (pump->config.ml_per_second > 0.0f) {
        float ml = (actual_time_ms / 1000.0f) * pump->config.ml_per_second;
        pump->stats.total_ml += ml;
    }
    
    pump->last_stop_time_ms = current_time_ms;
    pump->is_running = false;
    pump->state = PUMP_STATE_COOLDOWN;
    
    const char *pump_name = (pump_id == PUMP_ACID) ? "ACID" : "BASE";
    ESP_LOGI(TAG, "Pump %s stopped: %llu ms (GPIO %d)", 
             pump_name, (unsigned long long)actual_time_ms, pump->config.gpio_pin);
    
    return ESP_OK;
}

/**
 * @brief Обновление состояния cooldown
 */
static void pump_update_cooldown(pump_id_t pump_id) {
    pump_data_t *pump = &s_pumps[pump_id];
    
    if (pump->state == PUMP_STATE_COOLDOWN) {
        uint64_t now_ms = esp_timer_get_time() / 1000;
        if (now_ms >= pump->last_stop_time_ms + pump->config.min_off_time_ms) {
            pump->state = PUMP_STATE_OFF;
        }
    }
}

/**
 * @brief Callback таймера автоостановки
 */
static void pump_timer_callback(TimerHandle_t timer) {
    pump_id_t pump_id = (pump_id_t)(uintptr_t)pvTimerGetTimerID(timer);
    
    ESP_LOGD(TAG, "Timer callback for pump %d", pump_id);
    pump_stop_internal(pump_id);
}

bool pump_control_is_initialized(void) {
    return s_initialized;
}

