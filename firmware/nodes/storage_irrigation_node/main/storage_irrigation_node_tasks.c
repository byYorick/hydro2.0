/**
 * @file storage_irrigation_node_tasks.c
 * @brief FreeRTOS задачи для storage_irrigation_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - heartbeat_task_start_default - публикация heartbeat (общий компонент)
 * - task_sensor_scan - быстрый опрос level-switch и runtime-реакции
 * - task_current_poll - периодическая публикация level-switch telemetry
 * - task_pump_health - health-метрики насосов
 * 
 * Примечание: уровень баков публикуется через level-switch каналы.
 */

#include "storage_irrigation_node_app.h"
#include "storage_irrigation_node_config.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "pump_driver.h"
#include "storage_irrigation_node_framework_integration.h"
#include "node_telemetry_engine.h"
#include "node_utils.h"
#include "node_watchdog.h"
#include "heartbeat_task.h"
#include "esp_log.h"
#include "esp_idf_version.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "storage_irrigation_node_tasks";

// Периоды задач (в миллисекундах)
#define DEFAULT_CURRENT_POLL_MS   STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_POLL_INTERVAL_MS
#define SENSOR_SCAN_INTERVAL_MS    STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_SCAN_INTERVAL_MS
#define PUMP_HEALTH_INTERVAL_MS    10000 // 10 секунд - health отчеты
#define STATUS_PUBLISH_INTERVAL_MS 60000  // 60 секунд - публикация STATUS согласно DEVICE_NODE_PROTOCOL.md
#define TASK_WDT_RESET_SLICE_MS     1000

// Глобальная переменная для интервала публикации level-switch (потокобезопасно)
static uint32_t s_current_poll_interval_ms = DEFAULT_CURRENT_POLL_MS;
static SemaphoreHandle_t s_current_poll_interval_mutex = NULL;

/**
 * @brief Инициализация mutex для s_current_poll_interval_ms
 */
static void init_current_poll_interval_mutex(void) {
    if (s_current_poll_interval_mutex == NULL) {
        s_current_poll_interval_mutex = xSemaphoreCreateMutex();
        if (s_current_poll_interval_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create current poll interval mutex");
        }
    }
}

/**
 * @brief Потокобезопасное получение интервала опроса
 */
static uint32_t get_current_poll_interval(void) {
    init_current_poll_interval_mutex();
    uint32_t result = DEFAULT_CURRENT_POLL_MS;
    if (s_current_poll_interval_mutex != NULL && 
        xSemaphoreTake(s_current_poll_interval_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        result = s_current_poll_interval_ms;
        xSemaphoreGive(s_current_poll_interval_mutex);
    }
    return result;
}

/**
 * @brief Потокобезопасная установка интервала опроса
 */
static void set_current_poll_interval(uint32_t interval_ms) {
    init_current_poll_interval_mutex();
    if (s_current_poll_interval_mutex != NULL && 
        xSemaphoreTake(s_current_poll_interval_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        s_current_poll_interval_ms = interval_ms;
        xSemaphoreGive(s_current_poll_interval_mutex);
    }
}

/**
 * @brief Быстрая задача опроса датчиков уровня.
 *
 * Выполняет фактическое чтение датчиков, completion checks и обновление OLED
 * с фиксированным периодом 200 мс, без публикации telemetry на каждый тик.
 */
static void task_sensor_scan(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor scan task started");

    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add sensor scan task to watchdog: %s", esp_err_to_name(wdt_err));
    }

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(SENSOR_SCAN_INTERVAL_MS));
        node_watchdog_reset();
        (void)storage_irrigation_node_sensor_cycle(false);
        node_watchdog_reset();
    }
}

/**
 * @brief Задача публикации level-switch телеметрии
 * 
 * Интервал публикации берется из NodeConfig для канала "level_clean_min".
 * Фактическое состояние датчиков уже обновлено отдельной быстрой задачей.
 */
static void task_current_poll(void *pvParameters) {
    ESP_LOGI(TAG, "Current poll task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add current poll task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    while (1) {
        // Получаем актуальный интервал из конфигурации (потокобезопасно)
        uint32_t poll_interval = get_current_poll_interval();
        uint32_t waited_ms = 0;
        while (waited_ms < poll_interval) {
            uint32_t sleep_ms = poll_interval - waited_ms;
            if (sleep_ms > TASK_WDT_RESET_SLICE_MS) {
                sleep_ms = TASK_WDT_RESET_SLICE_MS;
            }
            vTaskDelay(pdMS_TO_TICKS(sleep_ms));
            waited_ms += sleep_ms;
            node_watchdog_reset();
        }

        node_watchdog_reset();

        // Публикация telemetry снимка по уже обновленному состоянию датчиков.
        storage_irrigation_node_publish_telemetry_callback(NULL);
        node_watchdog_reset();
    }
}

/**
 * @brief Задача публикации health-метрик насосов и INA209
 */
static void task_pump_health(void *pvParameters) {
    ESP_LOGI(TAG, "Pump health task started");

    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add pump health task to watchdog: %s", esp_err_to_name(wdt_err));
    }

    pump_driver_health_snapshot_t snapshot;

    while (1) {
        uint32_t waited_ms = 0;
        while (waited_ms < PUMP_HEALTH_INTERVAL_MS) {
            uint32_t sleep_ms = PUMP_HEALTH_INTERVAL_MS - waited_ms;
            if (sleep_ms > TASK_WDT_RESET_SLICE_MS) {
                sleep_ms = TASK_WDT_RESET_SLICE_MS;
            }
            vTaskDelay(pdMS_TO_TICKS(sleep_ms));
            waited_ms += sleep_ms;
            node_watchdog_reset();
        }

        node_watchdog_reset();

        if (!mqtt_manager_is_connected()) {
            continue;
        }

        esp_err_t err = pump_driver_get_health_snapshot(&snapshot);
        if (err != ESP_OK) {
            ESP_LOGD(TAG, "Health snapshot unavailable: %s", esp_err_to_name(err));
            continue;
        }

        cJSON *health = cJSON_CreateObject();
        if (!health) {
            continue;
        }

        cJSON_AddNumberToObject(health, "ts", (double)node_utils_get_timestamp_seconds());

        cJSON *channels = cJSON_CreateArray();
        if (!channels) {
            cJSON_Delete(health);
            continue;
        }

        for (size_t i = 0; i < snapshot.channel_count; i++) {
            const pump_driver_channel_health_t *ch = &snapshot.channels[i];
            cJSON *entry = cJSON_CreateObject();
            if (!entry) {
                continue;
            }

            cJSON_AddStringToObject(entry, "channel", ch->channel_name);
            cJSON_AddBoolToObject(entry, "running", ch->is_running);
            cJSON_AddBoolToObject(entry, "last_run_success", ch->last_run_success);
            cJSON_AddNumberToObject(entry, "last_run_ms", (double)ch->last_run_duration_ms);
            cJSON_AddNumberToObject(entry, "total_run_ms", (double)ch->total_run_time_ms);
            cJSON_AddNumberToObject(entry, "run_count", (double)ch->run_count);
            cJSON_AddNumberToObject(entry, "failure_count", (double)ch->failure_count);
            cJSON_AddNumberToObject(entry, "overcurrent_events", (double)ch->overcurrent_events);
            cJSON_AddNumberToObject(entry, "no_current_events", (double)ch->no_current_events);
            cJSON_AddNumberToObject(entry, "last_start_ts", (double)ch->last_start_timestamp_ms);
            cJSON_AddNumberToObject(entry, "last_stop_ts", (double)ch->last_stop_timestamp_ms);

            cJSON_AddItemToArray(channels, entry);
        }

        cJSON_AddItemToObject(health, "channels", channels);

        cJSON *ina = cJSON_CreateObject();
        if (ina) {
            cJSON_AddBoolToObject(ina, "enabled", snapshot.ina_status.enabled);
            cJSON_AddBoolToObject(ina, "reading_valid", snapshot.ina_status.last_read_valid);
            cJSON_AddBoolToObject(ina, "overcurrent", snapshot.ina_status.last_read_overcurrent);
            cJSON_AddBoolToObject(ina, "undercurrent", snapshot.ina_status.last_read_undercurrent);
            cJSON_AddNumberToObject(ina, "last_current_ma", snapshot.ina_status.last_current_ma);
            cJSON_AddItemToObject(health, "ina209", ina);
        }

        char *json_str = cJSON_PrintUnformatted(health);
        if (json_str) {
            mqtt_manager_publish_telemetry("pump_health", json_str);
            free(json_str);
        }

        cJSON_Delete(health);
        node_watchdog_reset();
    }
}

/**
 * @brief Задача публикации STATUS сообщений
 * 
 * Публикует status каждые 60 секунд согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 * 
 * Примечание: интервал 60 секунд больше watchdog таймаута (10 сек),
 * поэтому используем периодический сброс watchdog во время ожидания
 */
static void task_status(void *pvParameters) {
    ESP_LOGI(TAG, "Status task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add status task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(STATUS_PUBLISH_INTERVAL_MS);
    
    // Сбрасываем watchdog каждую секунду, чтобы иметь запас к системному таймауту
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(1000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        // Периодически сбрасываем watchdog во время ожидания
        // (интервал задачи 60 сек > watchdog таймаут 10 сек)
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для публикации STATUS
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();
            
            if (mqtt_manager_is_connected()) {
                // Публикация STATUS
                storage_irrigation_node_publish_status();
            }
            
            // Сбрасываем watchdog после выполнения работы
            node_watchdog_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/**
 * @brief Publish STATUS message
 * 
 * Публикует статус узла согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 */
void storage_irrigation_node_publish_status(void) {
    if (!mqtt_manager_is_connected()) {
        return;
    }

    // Канонический node-level status payload: {"status":"ONLINE","ts":...}
    cJSON *status = cJSON_CreateObject();
    if (status) {
        cJSON_AddStringToObject(status, "status", "ONLINE");
        cJSON_AddNumberToObject(status, "ts", (double)node_utils_get_timestamp_seconds());

        char *json_str = cJSON_PrintUnformatted(status);
        if (json_str) {
            mqtt_manager_publish_status(json_str);
            free(json_str);
        }
        cJSON_Delete(status);
    }
}

/**
 * @brief Обновление интервала опроса из NodeConfig
 * 
 * Ищет канал "level_clean_min" в NodeConfig и обновляет s_current_poll_interval_ms
 */
void storage_irrigation_node_update_current_poll_interval(void) {
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        ESP_LOGW(TAG, "Failed to load config for poll interval update");
        return;
    }
    
    cJSON *config = cJSON_Parse(config_json);
    if (config == NULL) {
        ESP_LOGW(TAG, "Failed to parse config for poll interval update");
        return;
    }
    
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels != NULL && cJSON_IsArray(channels)) {
        int channel_count = cJSON_GetArraySize(channels);
        for (int i = 0; i < channel_count; i++) {
            cJSON *ch = cJSON_GetArrayItem(channels, i);
            if (ch != NULL && cJSON_IsObject(ch)) {
                cJSON *name = cJSON_GetObjectItem(ch, "name");
                if (name != NULL && cJSON_IsString(name) && 
                    strcmp(name->valuestring, "level_clean_min") == 0) {
                    cJSON *poll_interval = cJSON_GetObjectItem(ch, "poll_interval_ms");
                    if (poll_interval != NULL && cJSON_IsNumber(poll_interval)) {
                        uint32_t new_interval = (uint32_t)cJSON_GetNumberValue(poll_interval);
                        set_current_poll_interval(new_interval);
                        ESP_LOGI(TAG, "Updated current poll interval to %lu ms", new_interval);
                    }
                    break;
                }
            }
        }
    }
    
    cJSON_Delete(config);
}

/**
 * @brief Запуск FreeRTOS задач
 */
void storage_irrigation_node_start_tasks(void) {
    // Обновляем интервал опроса из конфигурации
    storage_irrigation_node_update_current_poll_interval();

    BaseType_t task_ok = pdPASS;

    task_ok = xTaskCreate(
        task_sensor_scan,
        "sensor_scan_task",
        STORAGE_IRRIGATION_NODE_SENSOR_SCAN_TASK_STACK_WORDS,
        NULL,
        4,
        NULL
    );
    if (task_ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to create sensor_scan_task");
        return;
    }

    // task_current_poll теперь только публикует telemetry snapshot по медленному интервалу.
    task_ok = xTaskCreate(
        task_current_poll,
        "current_poll_task",
        STORAGE_IRRIGATION_NODE_CURRENT_POLL_TASK_STACK_WORDS,
        NULL,
        4,
        NULL
    );
    if (task_ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to create current_poll_task");
        return;
    }

    // pump_health_task собирает крупный JSON snapshot и требует заметно большего стека.
    task_ok = xTaskCreate(
        task_pump_health,
        "pump_health_task",
        STORAGE_IRRIGATION_NODE_PUMP_HEALTH_TASK_STACK_WORDS,
        NULL,
        4,
        NULL
    );
    if (task_ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to create pump_health_task");
        return;
    }

    task_ok = xTaskCreate(
        task_status,
        "status_task",
        STORAGE_IRRIGATION_NODE_STATUS_TASK_STACK_WORDS,
        NULL,
        3,
        NULL
    );
    if (task_ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to create status_task");
        return;
    }

    // Общая задача heartbeat из компонента
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}
