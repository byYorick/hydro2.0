/**
 * @file node_watchdog.c
 * @brief Реализация унифицированного менеджера watchdog
 */

#include "node_watchdog.h"
#include "node_state_manager.h"
#include "esp_task_wdt.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "node_watchdog";

// Конфигурация по умолчанию
#define DEFAULT_WATCHDOG_TIMEOUT_MS 10000  // 10 секунд
#define DEFAULT_TRIGGER_PANIC false         // Переход в safe_mode вместо panic

static struct {
    bool initialized;
    node_watchdog_config_t config;
} s_watchdog = {0};

// Примечание: обработка срабатывания watchdog без panic сложна в ESP-IDF
// Рекомендуется использовать trigger_panic=true и проверять причину перезагрузки
// в main() для перехода в safe_mode при следующей загрузке

esp_err_t node_watchdog_init(const node_watchdog_config_t *config) {
    if (s_watchdog.initialized) {
        ESP_LOGW(TAG, "Watchdog already initialized");
        return ESP_ERR_INVALID_STATE;
    }

    // Используем конфигурацию по умолчанию, если не указана
    node_watchdog_config_t default_config = {
        .timeout_ms = DEFAULT_WATCHDOG_TIMEOUT_MS,
        .trigger_panic = DEFAULT_TRIGGER_PANIC,
        .idle_core_mask = 0  // Не мониторим idle задачи
    };

    if (config != NULL) {
        s_watchdog.config = *config;
    } else {
        s_watchdog.config = default_config;
    }

    // Инициализация watchdog таймера
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = s_watchdog.config.timeout_ms,
        .idle_core_mask = s_watchdog.config.idle_core_mask,
        .trigger_panic = s_watchdog.config.trigger_panic
    };

    esp_err_t err = esp_task_wdt_init(&wdt_config);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Watchdog initialized (timeout: %lu ms, panic: %s)", 
                 s_watchdog.config.timeout_ms,
                 s_watchdog.config.trigger_panic ? "enabled" : "disabled");
        s_watchdog.initialized = true;
    } else if (err == ESP_ERR_INVALID_STATE) {
        // Watchdog уже инициализирован (возможно, ESP-IDF сделал это автоматически)
        ESP_LOGI(TAG, "Watchdog already initialized, using existing configuration");
        s_watchdog.initialized = true;
    } else {
        ESP_LOGE(TAG, "Failed to initialize watchdog: %s", esp_err_to_name(err));
        return err;
    }

    // Если trigger_panic отключен, нужно обработать срабатывание watchdog
    // через переход в safe_mode. Для этого используем idle hook или отдельную задачу
    // Но в ESP-IDF нет прямого способа перехватить срабатывание watchdog без panic
    // Поэтому рекомендуется использовать trigger_panic=false только для отладки
    // В production лучше использовать trigger_panic=true и обрабатывать через
    // перезагрузку и проверку причины перезагрузки в main()

    return ESP_OK;
}

esp_err_t node_watchdog_deinit(void) {
    if (!s_watchdog.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    // ESP-IDF не предоставляет функцию деинициализации watchdog
    // Можно только сбросить конфигурацию
    s_watchdog.initialized = false;
    ESP_LOGI(TAG, "Watchdog deinitialized");
    return ESP_OK;
}

esp_err_t node_watchdog_add_task(void) {
    if (!s_watchdog.initialized) {
        ESP_LOGW(TAG, "Watchdog not initialized, initializing with defaults");
        esp_err_t err = node_watchdog_init(NULL);
        if (err != ESP_OK) {
            return err;
        }
    }

    esp_err_t err = esp_task_wdt_add(NULL);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
        const char *task_name = pcTaskGetName(current_task);
        ESP_LOGE(TAG, "Failed to add task '%s' to watchdog: %s", 
                 task_name ? task_name : "unknown", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

esp_err_t node_watchdog_remove_task(void) {
    if (!s_watchdog.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = esp_task_wdt_delete(NULL);
    if (err != ESP_OK) {
        TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
        const char *task_name = pcTaskGetName(current_task);
        ESP_LOGW(TAG, "Failed to remove task '%s' from watchdog: %s", 
                 task_name ? task_name : "unknown", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

esp_err_t node_watchdog_reset(void) {
    if (!s_watchdog.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = esp_task_wdt_reset();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reset watchdog: %s", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

esp_err_t node_watchdog_get_task_runtime(const char *task_name, uint32_t *runtime_ms) {
    if (runtime_ms == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    TaskHandle_t task_handle = NULL;
    if (task_name == NULL) {
        task_handle = xTaskGetCurrentTaskHandle();
    } else {
        task_handle = xTaskGetHandle(task_name);
        if (task_handle == NULL) {
            ESP_LOGW(TAG, "Task '%s' not found", task_name);
            return ESP_ERR_NOT_FOUND;
        }
    }

    TaskStatus_t task_status;
    UBaseType_t task_num = uxTaskGetNumberOfTasks();
    TaskStatus_t *task_status_array = (TaskStatus_t *)pvPortMalloc(task_num * sizeof(TaskStatus_t));
    if (task_status_array == NULL) {
        return ESP_ERR_NO_MEM;
    }

    task_num = uxTaskGetSystemState(task_status_array, task_num, NULL);
    bool found = false;
    for (UBaseType_t i = 0; i < task_num; i++) {
        if (task_status_array[i].xHandle == task_handle) {
            task_status = task_status_array[i];
            found = true;
            break;
        }
    }

    vPortFree(task_status_array);

    if (!found) {
        return ESP_ERR_NOT_FOUND;
    }

    // Время работы задачи в миллисекундах
    *runtime_ms = (uint32_t)(task_status.ulRunTimeCounter * 1000 / configTICK_RATE_HZ);
    return ESP_OK;
}

bool node_watchdog_is_initialized(void) {
    return s_watchdog.initialized;
}

