/**
 * @file node_state_manager.c
 * @brief Реализация менеджера состояния ноды
 */

#include "node_state_manager.h"
#include "node_framework.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "cJSON.h"
#include <stdlib.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>

static const char *TAG = "node_state_manager";

#define MAX_ERROR_ENTRIES 32
#define COMPONENT_NAME_MAX_LEN 32

typedef struct {
    char component[COMPONENT_NAME_MAX_LEN];
    uint32_t error_count;
} error_counter_t;

static struct {
    bool initialized;
    error_counter_t errors[MAX_ERROR_ENTRIES];
    size_t error_count;
    SemaphoreHandle_t mutex;
    node_safe_mode_disable_actuators_callback_t safe_mode_callback;
    void *safe_mode_user_ctx;
} s_state_manager = {0};

esp_err_t node_state_manager_init(void) {
    if (s_state_manager.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    s_state_manager.mutex = xSemaphoreCreateMutex();
    if (s_state_manager.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }

    s_state_manager.initialized = true;
    ESP_LOGI(TAG, "State manager initialized");
    return ESP_OK;
}

esp_err_t node_state_manager_deinit(void) {
    if (!s_state_manager.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_state_manager.mutex) {
        vSemaphoreDelete(s_state_manager.mutex);
        s_state_manager.mutex = NULL;
    }

    memset(&s_state_manager, 0, sizeof(s_state_manager));
    ESP_LOGI(TAG, "State manager deinitialized");
    return ESP_OK;
}

esp_err_t node_state_manager_enter_safe_mode(const char *reason) {
    if (!s_state_manager.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGW(TAG, "Entering safe mode: %s", reason ? reason : "Unknown reason");

    // Отключаем все актуаторы через callback (если зарегистрирован)
    if (s_state_manager.safe_mode_callback) {
        esp_err_t callback_err = s_state_manager.safe_mode_callback(s_state_manager.safe_mode_user_ctx);
        if (callback_err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to disable actuators in safe mode: %s", esp_err_to_name(callback_err));
        }
    }

    // Устанавливаем состояние через фреймворк
    esp_err_t err = node_framework_set_state(NODE_STATE_SAFE_MODE);
    if (err != ESP_OK) {
        return err;
    }

    // Публикуем статус через MQTT (если подключен)
    if (mqtt_manager_is_connected()) {
        cJSON *status = cJSON_CreateObject();
        if (status) {
            cJSON_AddStringToObject(status, "state", "safe_mode");
            cJSON_AddStringToObject(status, "reason", reason ? reason : "Unknown");
            cJSON_AddNumberToObject(status, "ts", (double)(esp_timer_get_time() / 1000000));
            
            char *json_str = cJSON_PrintUnformatted(status);
            if (json_str) {
                mqtt_manager_publish_status(json_str);
                free(json_str);
            }
            cJSON_Delete(status);
        }
    }

    return ESP_OK;
}

esp_err_t node_state_manager_exit_safe_mode(void) {
    if (!s_state_manager.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Exiting safe mode");
    return node_framework_set_state(NODE_STATE_RUNNING);
}

// Новая версия с уровнями ошибок
esp_err_t node_state_manager_report_error(
    error_level_t level,
    const char *component,
    esp_err_t error_code,
    const char *message
) {
    if (!s_state_manager.initialized || component == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Логирование в зависимости от уровня
    const char *level_str;
    switch (level) {
        case ERROR_LEVEL_WARNING:
            ESP_LOGW(TAG, "[%s] Warning %s (0x%x): %s", 
                     component, 
                     esp_err_to_name(error_code),
                     error_code,
                     message ? message : "Unknown warning");
            level_str = "WARNING";
            break;
        case ERROR_LEVEL_ERROR:
            ESP_LOGE(TAG, "[%s] Error %s (0x%x): %s", 
                     component, 
                     esp_err_to_name(error_code),
                     error_code,
                     message ? message : "Unknown error");
            level_str = "ERROR";
            break;
        case ERROR_LEVEL_CRITICAL:
            ESP_LOGE(TAG, "[%s] CRITICAL Error %s (0x%x): %s", 
                     component, 
                     esp_err_to_name(error_code),
                     error_code,
                     message ? message : "Unknown critical error");
            level_str = "CRITICAL";
            break;
        default:
            ESP_LOGE(TAG, "[%s] Unknown level error %s (0x%x): %s", 
                     component, 
                     esp_err_to_name(error_code),
                     error_code,
                     message ? message : "Unknown error");
            level_str = "UNKNOWN";
            break;
    }

    // Отправка ошибки через MQTT (если подключен)
    if (mqtt_manager_is_connected()) {
        char node_id[64];
        if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
            cJSON *error_json = cJSON_CreateObject();
            if (error_json) {
                cJSON_AddStringToObject(error_json, "level", level_str);
                cJSON_AddStringToObject(error_json, "component", component);
                cJSON_AddStringToObject(error_json, "error_code", esp_err_to_name(error_code));
                cJSON_AddNumberToObject(error_json, "error_code_num", error_code);
                cJSON_AddStringToObject(error_json, "message", message ? message : "Unknown error");
                cJSON_AddNumberToObject(error_json, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(error_json);
                if (json_str) {
                    // Публикуем в топик ошибок: hydro/{gh}/{zone}/{node}/error
                    char topic[256];  // Увеличенный размер для безопасности
                    char gh_uid[64], zone_uid[64];
                    if (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK &&
                        config_storage_get_zone_uid(zone_uid, sizeof(zone_uid)) == ESP_OK) {
                        int len = snprintf(topic, sizeof(topic), "hydro/%s/%s/%s/error", 
                                          gh_uid, zone_uid, node_id);
                        if (len < 0 || len >= (int)sizeof(topic)) {
                            ESP_LOGW(TAG, "Topic too long, using fallback");
                            snprintf(topic, sizeof(topic), "hydro/+/+/%s/error", node_id);
                        }
                    } else {
                        // Fallback: используем только node_id
                        snprintf(topic, sizeof(topic), "hydro/+/+/%s/error", node_id);
                    }
                    
                    mqtt_manager_publish_raw(topic, json_str, 1, 0);  // QoS=1 для надежности
                    free(json_str);
                }
                cJSON_Delete(error_json);
            }
        }
    }

    // Обновляем счетчик ошибок
    if (s_state_manager.mutex && 
        xSemaphoreTake(s_state_manager.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        
        // Ищем существующий счетчик для компонента
        bool found = false;
        for (size_t i = 0; i < s_state_manager.error_count; i++) {
            if (strcmp(s_state_manager.errors[i].component, component) == 0) {
                s_state_manager.errors[i].error_count++;
                found = true;
                break;
            }
        }

        // Добавляем новый счетчик, если не найден
        if (!found && s_state_manager.error_count < MAX_ERROR_ENTRIES) {
            strncpy(s_state_manager.errors[s_state_manager.error_count].component, 
                   component, 
                   COMPONENT_NAME_MAX_LEN - 1);
            s_state_manager.errors[s_state_manager.error_count].component[COMPONENT_NAME_MAX_LEN - 1] = '\0';
            s_state_manager.errors[s_state_manager.error_count].error_count = 1;
            s_state_manager.error_count++;
        }

        xSemaphoreGive(s_state_manager.mutex);
    }

    // Если ошибка критическая, переходим в safe_mode
    if (level == ERROR_LEVEL_CRITICAL) {
        char reason[128];
        snprintf(reason, sizeof(reason), "%s: %s", component, message ? message : "Critical error");
        return node_state_manager_enter_safe_mode(reason);
    }

    // Для некритических ошибок переходим в состояние ERROR
    if (level == ERROR_LEVEL_ERROR && node_framework_get_state() == NODE_STATE_RUNNING) {
        node_framework_set_state(NODE_STATE_ERROR);
    }

    return ESP_OK;
}

// Старая версия для обратной совместимости
esp_err_t node_state_manager_report_error_legacy(
    const char *component,
    esp_err_t error_code,
    const char *message,
    bool is_critical
) {
    error_level_t level = is_critical ? ERROR_LEVEL_CRITICAL : ERROR_LEVEL_ERROR;
    return node_state_manager_report_error(level, component, error_code, message);
}

uint32_t node_state_manager_get_error_count(const char *component) {
    if (!s_state_manager.initialized) {
        return 0;
    }

    if (s_state_manager.mutex && 
        xSemaphoreTake(s_state_manager.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        
        uint32_t count = 0;

        if (component == NULL) {
            // Суммируем все ошибки
            for (size_t i = 0; i < s_state_manager.error_count; i++) {
                count += s_state_manager.errors[i].error_count;
            }
        } else {
            // Ищем ошибки для конкретного компонента
            for (size_t i = 0; i < s_state_manager.error_count; i++) {
                if (strcmp(s_state_manager.errors[i].component, component) == 0) {
                    count = s_state_manager.errors[i].error_count;
                    break;
                }
            }
        }

        xSemaphoreGive(s_state_manager.mutex);
        return count;
    }

    return 0;
}

esp_err_t node_state_manager_register_safe_mode_callback(
    node_safe_mode_disable_actuators_callback_t callback,
    void *user_ctx
) {
    if (!s_state_manager.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    s_state_manager.safe_mode_callback = callback;
    s_state_manager.safe_mode_user_ctx = user_ctx;
    ESP_LOGI(TAG, "Safe mode callback registered");
    return ESP_OK;
}

