/**
 * @file node_framework.c
 * @brief Реализация базового фреймворка для нод
 */

#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "node_watchdog.h"
#include "memory_pool.h"
#include "cJSON.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>

static const char *TAG = "node_framework";

// Глобальное состояние фреймворка
static struct {
    node_framework_config_t config;
    node_state_t state;
    bool initialized;
    SemaphoreHandle_t mutex;
} s_framework = {0};

// Forward declarations
static esp_err_t handle_exit_safe_mode(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
);

esp_err_t node_framework_init(const node_framework_config_t *config) {
    if (config == NULL) {
        ESP_LOGE(TAG, "Config is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    if (s_framework.initialized) {
        ESP_LOGW(TAG, "Framework already initialized");
        return ESP_ERR_INVALID_STATE;
    }

    // Создание mutex для защиты состояния
    s_framework.mutex = xSemaphoreCreateMutex();
    if (s_framework.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }

    // Копирование конфигурации
    memcpy(&s_framework.config, config, sizeof(node_framework_config_t));
    s_framework.state = NODE_STATE_INIT;
    s_framework.initialized = true;

    // Инициализация watchdog (должна быть первой, так как другие компоненты могут использовать её)
    node_watchdog_config_t wdt_config = {
        .timeout_ms = 10000,  // 10 секунд
        .trigger_panic = false,  // Переход в safe_mode вместо panic (обрабатывается через проверку причины перезагрузки)
        .idle_core_mask = 0  // Не мониторим idle задачи
    };
    esp_err_t err = node_watchdog_init(&wdt_config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to init watchdog: %s (continuing anyway)", esp_err_to_name(err));
        // Не критично, продолжаем инициализацию
    }

    // Инициализация пула памяти для оптимизации использования памяти
    err = memory_pool_init(NULL);  // Используем конфигурацию по умолчанию
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to init memory pool: %s (continuing anyway)", esp_err_to_name(err));
        // Не критично, продолжаем инициализацию
    }

    // Инициализация подкомпонентов
    err = node_state_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init state manager: %s", esp_err_to_name(err));
        goto cleanup;
    }

    // Инициализация движка телеметрии
    // Объявление функции из node_telemetry_engine.c
    extern esp_err_t node_telemetry_engine_init(void);
    err = node_telemetry_engine_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init telemetry engine: %s", esp_err_to_name(err));
        node_state_manager_deinit();
        goto cleanup;
    }

    // Регистрация callback для инициализации каналов в config_handler
    extern void node_config_handler_set_channel_init_callback(
        node_config_channel_callback_t callback,
        void *user_ctx
    );
    node_config_handler_set_channel_init_callback(config->channel_init_cb, config->user_ctx);

    // Регистрация встроенной команды exit_safe_mode
    extern esp_err_t node_command_handler_register(
        const char *cmd_name,
        node_command_handler_func_t handler,
        void *user_ctx
    );
    extern cJSON *node_command_handler_create_response(
        const char *cmd_id,
        const char *status,
        const char *error_code,
        const char *error_message,
        const cJSON *extra_data
    );
    extern esp_err_t node_state_manager_exit_safe_mode(void);
    
    err = node_command_handler_register("exit_safe_mode", handle_exit_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register exit_safe_mode command: %s", esp_err_to_name(err));
        // Не критично, продолжаем инициализацию
    }

    // Инициализация пула памяти для оптимизации использования памяти
    err = memory_pool_init(NULL);  // Используем конфигурацию по умолчанию
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to init memory pool: %s (continuing anyway)", esp_err_to_name(err));
        // Не критично, продолжаем инициализацию
    }

    ESP_LOGI(TAG, "Node framework initialized (node_type: %s)", config->node_type);
    return ESP_OK;

cleanup:
    if (s_framework.mutex) {
        vSemaphoreDelete(s_framework.mutex);
        s_framework.mutex = NULL;
    }
    s_framework.initialized = false;
    return err;
}

esp_err_t node_framework_deinit(void) {
    if (!s_framework.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    // Деинициализация подкомпонентов
    extern esp_err_t node_telemetry_engine_deinit(void);
    node_telemetry_engine_deinit();
    node_state_manager_deinit();

    if (s_framework.mutex) {
        vSemaphoreDelete(s_framework.mutex);
        s_framework.mutex = NULL;
    }

    memset(&s_framework, 0, sizeof(s_framework));
    ESP_LOGI(TAG, "Node framework deinitialized");
    return ESP_OK;
}

node_state_t node_framework_get_state(void) {
    if (!s_framework.initialized || s_framework.mutex == NULL) {
        return NODE_STATE_INIT;
    }

    if (xSemaphoreTake(s_framework.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        node_state_t state = s_framework.state;
        xSemaphoreGive(s_framework.mutex);
        return state;
    }

    return NODE_STATE_INIT;
}

esp_err_t node_framework_set_state(node_state_t state) {
    if (!s_framework.initialized || s_framework.mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_framework.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        node_state_t old_state = s_framework.state;
        s_framework.state = state;
        xSemaphoreGive(s_framework.mutex);

        ESP_LOGI(TAG, "State changed: %d -> %d", old_state, state);
        return ESP_OK;
    }

    return ESP_ERR_TIMEOUT;
}

bool node_framework_is_safe_mode(void) {
    return node_framework_get_state() == NODE_STATE_SAFE_MODE;
}

// Обработчик команды exit_safe_mode
static esp_err_t handle_exit_safe_mode(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)params;
    (void)user_ctx;
    
    extern esp_err_t node_state_manager_exit_safe_mode(void);
    extern cJSON *node_command_handler_create_response(
        const char *cmd_id,
        const char *status,
        const char *error_code,
        const char *error_message,
        const cJSON *extra_data
    );
    
    esp_err_t err = node_state_manager_exit_safe_mode();
    if (err == ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,  // cmd_id будет добавлен автоматически
            "ACK",
            NULL,
            NULL,
            NULL
        );
    } else {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "exit_safe_mode_failed",
            "Failed to exit safe mode",
            NULL
        );
    }
    return err;
}

