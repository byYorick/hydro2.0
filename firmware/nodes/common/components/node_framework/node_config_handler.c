/**
 * @file node_config_handler.c
 * @brief Реализация обработчика NodeConfig
 */

#include "node_config_handler.h"
#include "node_framework.h"
#include "node_utils.h"
#include "config_storage.h"
#include "config_apply.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <limits.h>

// Forward declarations для типов из mqtt_manager.h
typedef void (*mqtt_config_callback_t)(const char *topic, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_command_callback_t)(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_connection_callback_t)(bool connected, void *user_ctx);

static const char *TAG = "node_config_handler";

// Глобальная ссылка на callback для инициализации каналов
static node_config_channel_callback_t s_channel_init_cb = NULL;
static void *s_channel_init_ctx = NULL;

// Глобальные ссылки на MQTT callbacks для config_apply_mqtt
static mqtt_config_callback_t s_mqtt_config_cb = NULL;
static mqtt_command_callback_t s_mqtt_command_cb = NULL;
static mqtt_connection_callback_t s_mqtt_connection_cb = NULL;
static void *s_mqtt_user_ctx = NULL;
static const char *s_default_node_id = NULL;
static const char *s_default_gh_uid = NULL;
static const char *s_default_zone_uid = NULL;

// Очередь для обработки конфигов (чтобы избежать переполнения стека в MQTT callback)
// КРИТИЧНО: Увеличиваем размер очереди, так как после setup_portal конфиг может прийти несколько раз
// (retain сообщение + прямая публикация + возможные дубли при переподписке)
#define CONFIG_QUEUE_SIZE 10  // Увеличено с 2 до 10 для обработки burst конфигов после setup
#define CONFIG_PROCESSOR_STACK_SIZE 16384  // Увеличенный размер стека для обработки конфигов (16KB)

typedef struct {
    char *topic;
    char *data;
    int data_len;
    void *user_ctx;
} config_queue_item_t;

static QueueHandle_t s_config_queue = NULL;
static TaskHandle_t s_config_processor_task = NULL;
static bool s_config_processor_running = false;

/**
 * @brief Маскирует секретные поля в JSON перед логированием
 * 
 * @param json_str Исходная JSON строка
 * @param masked_buf Буфер для маскированной строки
 * @param buf_size Размер буфера
 * @return true если успешно, false при ошибке
 */
static bool mask_sensitive_json_fields(const char *json_str, char *masked_buf, size_t buf_size) {
    if (json_str == NULL || masked_buf == NULL || buf_size == 0) {
        return false;
    }
    
    // Безопасная проверка длины входной строки
    size_t json_str_len = strlen(json_str);
    if (json_str_len >= buf_size) {
        // Строка слишком длинная, не можем безопасно скопировать
        ESP_LOGW(TAG, "JSON string too long for mask buffer: %zu bytes, buffer: %zu", json_str_len, buf_size);
        return false;
    }
    
    cJSON *json = cJSON_Parse(json_str);
    if (json == NULL) {
        // Если не удалось распарсить, просто копируем строку (может быть не JSON)
        // Безопасное копирование с учетом проверки длины выше
        strncpy(masked_buf, json_str, buf_size - 1);
        masked_buf[buf_size - 1] = '\0';
        return true;
    }
    
    // Маскируем секретные поля
    const char *sensitive_fields[] = {"password", "pass", "pin", "token", "secret"};
    const size_t num_fields = sizeof(sensitive_fields) / sizeof(sensitive_fields[0]);
    
    for (size_t i = 0; i < num_fields; i++) {
        cJSON *item = cJSON_GetObjectItem(json, sensitive_fields[i]);
        if (item != NULL && cJSON_IsString(item)) {
            cJSON_SetValuestring(item, "[MASKED]");
        }
        
        // Также проверяем вложенные объекты (wifi.password, mqtt.password и т.д.)
        cJSON *wifi = cJSON_GetObjectItem(json, "wifi");
        if (wifi != NULL && cJSON_IsObject(wifi)) {
            cJSON *wifi_item = cJSON_GetObjectItem(wifi, sensitive_fields[i]);
            if (wifi_item != NULL && cJSON_IsString(wifi_item)) {
                cJSON_SetValuestring(wifi_item, "[MASKED]");
            }
        }
        
        cJSON *mqtt = cJSON_GetObjectItem(json, "mqtt");
        if (mqtt != NULL && cJSON_IsObject(mqtt)) {
            cJSON *mqtt_item = cJSON_GetObjectItem(mqtt, sensitive_fields[i]);
            if (mqtt_item != NULL && cJSON_IsString(mqtt_item)) {
                cJSON_SetValuestring(mqtt_item, "[MASKED]");
            }
        }
    }
    
    char *masked_json = cJSON_PrintUnformatted(json);
    if (masked_json != NULL) {
        size_t masked_len = strlen(masked_json);
        // Проверяем, что результат помещается в буфер
        if (masked_len < buf_size) {
            strncpy(masked_buf, masked_json, buf_size - 1);
            masked_buf[buf_size - 1] = '\0';
            free(masked_json);
            cJSON_Delete(json);
            return true;
        } else {
            // Результат не помещается в буфер - это ошибка
            ESP_LOGW(TAG, "Masked JSON too large for buffer: %zu bytes, buffer: %zu", masked_len, buf_size);
            free(masked_json);
            cJSON_Delete(json);
            return false;
        }
    }
    
    cJSON_Delete(json);
    return false;
}

/**
 * @brief Внутренняя функция обработки конфига (вызывается из задачи)
 */
static void node_config_handler_process_internal(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    if (data == NULL || data_len <= 0) {
        // Игнорируем пустые/некорректные сообщения конфига, чтобы не сыпать ERROR
        ESP_LOGW(TAG, "Config message is empty, ignoring");
        return;
    }

    // Безопасность: маскируем секретные поля перед логированием
    // КРИТИЧНО: Используем локальный буфер вместо статического для потокобезопасности
    // Функция вызывается только из одной задачи последовательно, но fallback может вызвать из другого потока
    char masked_data[512];  // Уменьшенный размер для экономии стека задачи
    memset(masked_data, 0, sizeof(masked_data));
    
    // Проверяем длину с учетом null-terminator
    // КРИТИЧНО: data может быть не null-terminated, поэтому создаем временную копию для mask_sensitive_json_fields
    // которая ожидает null-terminated строку
    if (data_len > 0 && data_len < sizeof(masked_data) - 1) {
        // Создаем временную null-terminated копию для маскирования
        char temp_data[512];
        if (data_len < sizeof(temp_data)) {
            memcpy(temp_data, data, data_len);
            temp_data[data_len] = '\0';
            if (mask_sensitive_json_fields(temp_data, masked_data, sizeof(masked_data))) {
                ESP_LOGI(TAG, "Config received on %s: %s", topic ? topic : "NULL", masked_data);
            } else {
                ESP_LOGI(TAG, "Config received on %s: [%d bytes]", topic ? topic : "NULL", data_len);
            }
        } else {
            ESP_LOGI(TAG, "Config received on %s: [%d bytes]", topic ? topic : "NULL", data_len);
        }
    } else {
        // Если данные слишком большие, логируем только топик и длину
        ESP_LOGI(TAG, "Config received on %s: [%d bytes]", topic ? topic : "NULL", data_len);
    }

    // Парсинг JSON
    // КРИТИЧНО: cJSON_ParseWithLength корректно обрабатывает не null-terminated строки по data_len
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        node_config_handler_publish_response("ERROR", "Invalid JSON", NULL, 0);
        return;
    }

    // Валидация
    char error_msg[256];
    esp_err_t validate_err = node_config_handler_validate(config, error_msg, sizeof(error_msg));
    if (validate_err != ESP_OK) {
        ESP_LOGE(TAG, "Config validation failed: %s", error_msg);
        cJSON_Delete(config);
        node_config_handler_publish_response("ERROR", error_msg, NULL, 0);
        return;
    }

    // КРИТИЧНО: Проверяем, находится ли узел в временном режиме (после setup)
    // Если узел в временном режиме (gh-temp/zn-temp), конфиг от MQTT не должен применяться автоматически
    // Конфиг применяется только когда пользователь явно привязывает узел к зоне (через кнопку "Привязать")
    char current_gh_uid[64] = {0};
    char current_zone_uid[64] = {0};
    bool is_temp_mode = false;
    
    // BUGFIX: Проверяем оба значения отдельно, чтобы не пропустить временный режим
    // если одна из функций вернула ошибку, но другая успешно загрузила временное значение
    esp_err_t gh_err = config_storage_get_gh_uid(current_gh_uid, sizeof(current_gh_uid));
    esp_err_t zone_err = config_storage_get_zone_uid(current_zone_uid, sizeof(current_zone_uid));
    
    // Проверяем, находится ли узел в временном режиме
    // Считаем режим временным, если хотя бы одно из значений временное
    if (gh_err == ESP_OK && strcmp(current_gh_uid, "gh-temp") == 0) {
        is_temp_mode = true;
    }
    if (zone_err == ESP_OK && strcmp(current_zone_uid, "zn-temp") == 0) {
        is_temp_mode = true;
    }
    
    if (is_temp_mode) {
        ESP_LOGI(TAG, "Node is in temporary mode (gh_uid=%s, zone_uid=%s)", current_gh_uid, current_zone_uid);
        
        // Получаем значения из нового конфига
        cJSON *new_gh_uid = cJSON_GetObjectItem(config, "gh_uid");
        cJSON *new_zone_uid = cJSON_GetObjectItem(config, "zone_uid");
        
        bool new_is_temp = false;
        if (new_gh_uid && cJSON_IsString(new_gh_uid) && new_gh_uid->valuestring) {
            new_is_temp = (strcmp(new_gh_uid->valuestring, "gh-temp") == 0);
        }
        if (!new_is_temp && new_zone_uid && cJSON_IsString(new_zone_uid) && new_zone_uid->valuestring) {
            new_is_temp = (strcmp(new_zone_uid->valuestring, "zn-temp") == 0);
        }
        
        // Если новый конфиг тоже временный - не применяем (игнорируем автоматические конфиги)
        if (new_is_temp) {
            ESP_LOGI(TAG, "Ignoring config from MQTT: node is in temporary mode and new config is also temporary (waiting for user binding)");
            cJSON_Delete(config);
            node_config_handler_publish_response("ACK", "Config received but not applied (temporary mode)", NULL, 0);
            return;
        } else {
            // Новый конфиг имеет реальные значения - это привязка от пользователя, применяем
            ESP_LOGI(TAG, "Applying config: node was in temporary mode but new config has real zone assignment (user binding)");
        }
    }

    // Загрузка предыдущего конфига
    cJSON *previous_config = config_apply_load_previous_config();

    // Применение конфигурации с получением результата о перезапущенных компонентах
    config_apply_result_t result;
    config_apply_result_init(&result);
    
    esp_err_t apply_err = node_config_handler_apply_with_result(config, previous_config, &result);
    if (apply_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to apply config: %s", esp_err_to_name(apply_err));
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        node_config_handler_publish_response("ERROR", "Failed to apply config", NULL, 0);
        return;
    }

    // ВАЖНО: Обновляем node_info в mqtt_manager после применения конфига,
    // чтобы config_response отправлялся на правильный топик с актуальными gh_uid и zone_uid
    // Это критично, так как нода может получить конфиг на временный топик,
    // но должна отправить config_response на правильный топик с реальными gh_uid и zone_uid
    char gh_uid[64] = {0};
    char zone_uid[64] = {0};
    char node_uid[64] = {0};
    
    // Получаем актуальные значения из сохраненного конфига
    if (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK && gh_uid[0] != '\0') {
        if (config_storage_get_zone_uid(zone_uid, sizeof(zone_uid)) == ESP_OK && zone_uid[0] != '\0') {
            if (config_storage_get_node_id(node_uid, sizeof(node_uid)) == ESP_OK && node_uid[0] != '\0') {
                // Обновляем node_info в mqtt_manager
                mqtt_node_info_t node_info = {
                    .gh_uid = gh_uid,
                    .zone_uid = zone_uid,
                    .node_uid = node_uid
                };
                esp_err_t update_err = mqtt_manager_update_node_info(&node_info);
                if (update_err == ESP_OK) {
                    ESP_LOGI(TAG, "Updated mqtt_manager node_info: gh_uid=%s, zone_uid=%s, node_uid=%s", 
                            gh_uid, zone_uid, node_uid);
                } else {
                    ESP_LOGW(TAG, "Failed to update mqtt_manager node_info: %s", esp_err_to_name(update_err));
                }
            }
        }
    }

    // Успешное применение - публикуем ACK с информацией о перезапущенных компонентах
    // Используем result из config_apply
    const char *restarted[CONFIG_APPLY_MAX_COMPONENTS];
    size_t restarted_count = 0;
    
    // Копируем компоненты из result
    for (size_t i = 0; i < result.count && i < CONFIG_APPLY_MAX_COMPONENTS; i++) {
        restarted[i] = result.components[i];
        restarted_count++;
    }
    
    // Если ничего не перезапускалось, публикуем пустой массив
    node_config_handler_publish_response("ACK", NULL, 
                                         restarted_count > 0 ? restarted : NULL, 
                                         restarted_count);

    cJSON_Delete(config);
    if (previous_config) {
        cJSON_Delete(previous_config);
    }
}

/**
 * @brief Задача обработки конфигов из очереди
 */
static void task_config_processor(void *pvParameters) {
    ESP_LOGI(TAG, "Config processor task started");
    s_config_processor_running = true;
    
    config_queue_item_t item;
    
    while (1) {
        // Получаем конфиг из очереди
        if (xQueueReceive(s_config_queue, &item, portMAX_DELAY) == pdTRUE) {
            // Обрабатываем конфиг
            node_config_handler_process_internal(item.topic, item.data, item.data_len, item.user_ctx);
            
            // Освобождаем память
            if (item.topic) free(item.topic);
            if (item.data) free(item.data);
        }
    }
}

/**
 * @brief Инициализация очереди конфигов
 */
static esp_err_t init_config_queue(void) {
    if (s_config_queue != NULL) {
        return ESP_OK;
    }
    
    s_config_queue = xQueueCreate(CONFIG_QUEUE_SIZE, sizeof(config_queue_item_t));
    if (s_config_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create config queue");
        return ESP_ERR_NO_MEM;
    }
    
    // Создаем задачу обработки конфигов
    BaseType_t ret = xTaskCreate(
        task_config_processor,
        "config_proc",
        CONFIG_PROCESSOR_STACK_SIZE,
        NULL,
        5,  // Средний приоритет для обработки конфигов
        &s_config_processor_task
    );
    
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create config processor task");
        vQueueDelete(s_config_queue);
        s_config_queue = NULL;
        return ESP_ERR_NO_MEM;
    }
    
    ESP_LOGI(TAG, "Config queue initialized (size: %d, stack: %d)", CONFIG_QUEUE_SIZE, CONFIG_PROCESSOR_STACK_SIZE);
    return ESP_OK;
}

/**
 * @brief Публичная функция обработки конфига (добавляет в очередь)
 */
void node_config_handler_process(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    // Инициализация очереди при первом вызове
    if (s_config_queue == NULL) {
        esp_err_t err = init_config_queue();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize config queue");
            // КРИТИЧНО: НЕ обрабатываем напрямую, так как это может вызвать переполнение стека
            // и гонку данных со статическими буферами. Вместо этого отправляем ошибку.
            node_config_handler_publish_response("ERROR", "Config queue initialization failed", NULL, 0);
            return;
        }
    }
    
    // Выделяем память для данных
    char *topic_copy = NULL;
    char *data_copy = NULL;
    
    if (topic) {
        topic_copy = strdup(topic);
        if (topic_copy == NULL) {
            ESP_LOGE(TAG, "Failed to allocate memory for topic");
            return;
        }
    }
    
    if (data && data_len > 0) {
        // КРИТИЧНО: Проверяем максимальный размер для предотвращения переполнения при malloc
        // Ограничиваем размер конфига максимальным размером JSON
        const size_t max_config_size = CONFIG_STORAGE_MAX_JSON_SIZE;
        if (data_len > max_config_size) {
            ESP_LOGE(TAG, "Config data too large: %d bytes (max: %zu)", data_len, max_config_size);
            if (topic_copy) free(topic_copy);
            node_config_handler_publish_response("ERROR", "Config too large", NULL, 0);
            return;
        }
        
        // Проверяем на переполнение при выделении памяти
        if (data_len > SIZE_MAX - 1) {
            ESP_LOGE(TAG, "Config data size overflow: %d bytes", data_len);
            if (topic_copy) free(topic_copy);
            node_config_handler_publish_response("ERROR", "Config size overflow", NULL, 0);
            return;
        }
        
        data_copy = malloc(data_len + 1);
        if (data_copy == NULL) {
            ESP_LOGE(TAG, "Failed to allocate memory for data (%d bytes)", data_len);
            if (topic_copy) free(topic_copy);
            return;
        }
        memcpy(data_copy, data, data_len);
        data_copy[data_len] = '\0';
    }
    
    // Создаем элемент очереди
    config_queue_item_t item = {
        .topic = topic_copy,
        .data = data_copy,
        .data_len = data_len,
        .user_ctx = user_ctx
    };
    
    // Добавляем в очередь (неблокирующий режим)
    if (xQueueSend(s_config_queue, &item, 0) != pdTRUE) {
        ESP_LOGW(TAG, "Config queue is full, dropping config");
        if (topic_copy) free(topic_copy);
        if (data_copy) free(data_copy);
        node_config_handler_publish_response("ERROR", "Config queue full", NULL, 0);
    }
}

esp_err_t node_config_handler_validate(
    const cJSON *config,
    char *error_msg,
    size_t error_msg_size
) {
    if (config == NULL || error_msg == NULL || error_msg_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    // Проверка обязательных полей
    cJSON *node_id = cJSON_GetObjectItem(config, "node_id");
    cJSON *version = cJSON_GetObjectItem(config, "version");
    cJSON *type = cJSON_GetObjectItem(config, "type");
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    cJSON *mqtt = cJSON_GetObjectItem(config, "mqtt");

    if (!cJSON_IsString(node_id)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid node_id");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsNumber(version)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid version");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsString(type)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid type");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsArray(channels)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid channels");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsObject(mqtt)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid mqtt");
        return ESP_ERR_INVALID_ARG;
    }

    // ВАЖНО: Если mqtt содержит только {"configured": true}, значит нода уже подключена
    // и backend НЕ хочет менять MQTT настройки. Пропускаем валидацию полей.
    cJSON *mqtt_configured = cJSON_GetObjectItem(mqtt, "configured");
    if (cJSON_IsBool(mqtt_configured) && cJSON_IsTrue(mqtt_configured)) {
        // Backend указал, что MQTT уже настроен - пропускаем валидацию host/port
        // Это предотвращает переподключение к MQTT, если нода уже работает
        ESP_LOGI(TAG, "MQTT marked as 'configured', preserving existing settings");
    } else {
        // Валидация обязательных MQTT полей только если это полная конфигурация
        cJSON *mqtt_host = cJSON_GetObjectItem(mqtt, "host");
        if (!cJSON_IsString(mqtt_host) || mqtt_host->valuestring == NULL || mqtt_host->valuestring[0] == '\0') {
            snprintf(error_msg, error_msg_size, "Missing or invalid mqtt.host");
            return ESP_ERR_INVALID_ARG;
        }
        
        cJSON *mqtt_port = cJSON_GetObjectItem(mqtt, "port");
        if (!cJSON_IsNumber(mqtt_port) || cJSON_GetNumberValue(mqtt_port) <= 0 || cJSON_GetNumberValue(mqtt_port) > 65535) {
            snprintf(error_msg, error_msg_size, "Missing or invalid mqtt.port (must be 1-65535)");
            return ESP_ERR_INVALID_ARG;
        }
        
        cJSON *mqtt_keepalive = cJSON_GetObjectItem(mqtt, "keepalive");
        if (mqtt_keepalive != NULL && (!cJSON_IsNumber(mqtt_keepalive) || cJSON_GetNumberValue(mqtt_keepalive) <= 0 || cJSON_GetNumberValue(mqtt_keepalive) > 65535)) {
            snprintf(error_msg, error_msg_size, "Invalid mqtt.keepalive (must be 1-65535)");
            return ESP_ERR_INVALID_ARG;
        }
    }

    // Дополнительная валидация через config_storage
    // КРИТИЧНО: cJSON_PrintUnformatted может выделить большой блок памяти
    // Ограничиваем размер для предотвращения проблем с памятью
    char *json_str = cJSON_PrintUnformatted(config);
    if (json_str) {
        size_t json_len = strlen(json_str);
        
        // Проверяем, что размер JSON не превышает максимальный размер конфигурации
        if (json_len >= CONFIG_STORAGE_MAX_JSON_SIZE) {
            ESP_LOGE(TAG, "Config JSON too large for validation: %zu bytes", json_len);
            free(json_str);
            snprintf(error_msg, error_msg_size, "Config too large (%zu bytes, max: %d)", 
                    json_len, CONFIG_STORAGE_MAX_JSON_SIZE - 1);
            return ESP_ERR_INVALID_SIZE;
        }
        
        char storage_error_msg[128];
        esp_err_t err = config_storage_validate(json_str, json_len, 
                                               storage_error_msg, sizeof(storage_error_msg));
        free(json_str);
        
        if (err != ESP_OK) {
            snprintf(error_msg, error_msg_size, "%s", storage_error_msg);
            return err;
        }
    } else {
        ESP_LOGE(TAG, "Failed to serialize config for validation");
        snprintf(error_msg, error_msg_size, "Failed to serialize config");
        return ESP_ERR_NO_MEM;
    }

    return ESP_OK;
}

esp_err_t node_config_handler_apply(
    const cJSON *config,
    const cJSON *previous_config
) {
    return node_config_handler_apply_with_result(config, previous_config, NULL);
}

esp_err_t node_config_handler_apply_with_result(
    const cJSON *config,
    const cJSON *previous_config,
    config_apply_result_t *result
) {
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t first_err = ESP_OK;

    // Сохранение конфига в NVS
    char *json_str = cJSON_PrintUnformatted(config);
    if (!json_str) {
        ESP_LOGE(TAG, "Failed to serialize config to JSON");
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = config_storage_save(json_str, strlen(json_str));
    free(json_str);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config to NVS: %s", esp_err_to_name(err));
        return err;
    }

    // Применение через config_apply
    config_apply_result_t local_result;
    config_apply_result_t *result_ptr = result ? result : &local_result;
    config_apply_result_init(result_ptr);

    // Подготовка MQTT параметров (если callbacks зарегистрированы)
    const config_apply_mqtt_params_t *mqtt_params = NULL;
    config_apply_mqtt_params_t mqtt_params_local = {0};
    if (s_mqtt_config_cb || s_mqtt_command_cb || s_mqtt_connection_cb) {
        mqtt_params_local = (config_apply_mqtt_params_t){
            .default_node_id = s_default_node_id ? s_default_node_id : "nd-unknown",
            .default_gh_uid = s_default_gh_uid ? s_default_gh_uid : "gh-1",
            .default_zone_uid = s_default_zone_uid ? s_default_zone_uid : "zn-1",
            .config_cb = s_mqtt_config_cb,
            .command_cb = s_mqtt_command_cb,
            .connection_cb = s_mqtt_connection_cb,
            .user_ctx = s_mqtt_user_ctx,
        };
        mqtt_params = &mqtt_params_local;
    }

    // Применение Wi-Fi конфига с автоматическим рестартом MQTT
    if (mqtt_params != NULL) {
        err = config_apply_wifi_with_mqtt_restart(config, previous_config, mqtt_params, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply Wi-Fi config: %s", esp_err_to_name(err));
            if (first_err == ESP_OK) {
                first_err = err;
            }
        }
    } else {
        err = config_apply_wifi(config, previous_config, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply Wi-Fi config: %s", esp_err_to_name(err));
            if (first_err == ESP_OK) {
                first_err = err;
            }
        }
    }

    // Применение MQTT конфига (если callbacks зарегистрированы)
    // Это нужно для случаев, когда меняются именно MQTT настройки (не Wi-Fi)
    if (mqtt_params != NULL) {
        err = config_apply_mqtt(config, previous_config, mqtt_params, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply MQTT config: %s", esp_err_to_name(err));
            if (first_err == ESP_OK) {
                first_err = err;
            }
        }
    } else {
        ESP_LOGW(TAG, "MQTT callbacks not registered, skipping MQTT config apply");
    }

    // Применение насосов (после инициализации каналов через callback)
    err = config_apply_channels_pump(result_ptr);
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to apply pump channels: %s", esp_err_to_name(err));
        if (first_err == ESP_OK) {
            first_err = err;
        }
    }

    // Инициализация каналов через callback
    if (s_channel_init_cb) {
        cJSON *channels = cJSON_GetObjectItem(config, "channels");
        if (cJSON_IsArray(channels)) {
            cJSON *channel = NULL;
            cJSON_ArrayForEach(channel, channels) {
                if (cJSON_IsObject(channel)) {
                    cJSON *name = cJSON_GetObjectItem(channel, "name");
                    if (cJSON_IsString(name)) {
                        esp_err_t channel_err = s_channel_init_cb(
                            name->valuestring,
                            channel,
                            s_channel_init_ctx
                        );
                        if (channel_err != ESP_OK) {
                            ESP_LOGW(TAG, "Failed to init channel %s: %s", 
                                    name->valuestring, esp_err_to_name(channel_err));
                        }
                    }
                }
            }
        }
    }

    return first_err;
}

esp_err_t node_config_handler_publish_response(
    const char *status,
    const char *error_msg,
    const char **restarted_components,
    size_t component_count
) {
    cJSON *response = cJSON_CreateObject();
    if (!response) {
        return ESP_ERR_NO_MEM;
    }

    cJSON_AddStringToObject(response, "status", status);
    cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());

    if (error_msg && strcmp(status, "ERROR") == 0) {
        cJSON_AddStringToObject(response, "error", error_msg);
    }

    if (restarted_components && component_count > 0 && strcmp(status, "ACK") == 0) {
        cJSON *restarted = cJSON_CreateArray();
        if (restarted) {
            bool all_added = true;
            for (size_t i = 0; i < component_count; i++) {
                cJSON *item = cJSON_CreateString(restarted_components[i] ? restarted_components[i] : "");
                if (item) {
                    cJSON_AddItemToArray(restarted, item);
                } else {
                    ESP_LOGE(TAG, "Failed to create string for restarted component %zu", i);
                    all_added = false;
                    break;
                }
            }
            if (all_added) {
                cJSON_AddItemToObject(response, "restarted", restarted);
            } else {
                // Если не удалось добавить все компоненты, удаляем массив
                cJSON_Delete(restarted);
            }
        }
    }

    char *json_str = cJSON_PrintUnformatted(response);
    if (json_str) {
        esp_err_t err = mqtt_manager_publish_config_response(json_str);
        free(json_str);
        cJSON_Delete(response);
        return err;
    }

    cJSON_Delete(response);
    return ESP_ERR_NO_MEM;
}

// Функция для регистрации callback инициализации каналов (используется из node_framework)
// Объявлена в node_framework.h, реализована здесь
void node_config_handler_set_channel_init_callback(
    node_config_channel_callback_t callback,
    void *user_ctx
) {
    s_channel_init_cb = callback;
    s_channel_init_ctx = user_ctx;
}

void node_config_handler_set_mqtt_callbacks(
    mqtt_config_callback_t config_cb,
    mqtt_command_callback_t command_cb,
    mqtt_connection_callback_t connection_cb,
    void *user_ctx,
    const char *default_node_id,
    const char *default_gh_uid,
    const char *default_zone_uid
) {
    s_mqtt_config_cb = config_cb;
    s_mqtt_command_cb = command_cb;
    s_mqtt_connection_cb = connection_cb;
    s_mqtt_user_ctx = user_ctx;
    s_default_node_id = default_node_id;
    s_default_gh_uid = default_gh_uid;
    s_default_zone_uid = default_zone_uid;
}
