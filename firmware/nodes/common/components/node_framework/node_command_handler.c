/**
 * @file node_command_handler.c
 * @brief Реализация обработчика команд
 */

#include "node_command_handler.h"
#include "node_framework.h"
#include "mqtt_manager.h"
#include "node_utils.h"
#include "oled_ui.h"
#include "config_storage.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "mbedtls/md.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static const char *TAG = "node_command_handler";
static bool g_logged_missing_hmac = false;
static const char *IN_PROGRESS_STATUS = "IN_PROGRESS";
static esp_timer_handle_t s_restart_timer = NULL;

// Константы для HMAC проверки
#define HMAC_TIMESTAMP_TOLERANCE_SEC 10  // Допустимое отклонение timestamp (секунды)
#define NODE_COMMAND_MAX_JSON_SIZE 4096  // Защита от слишком больших команд
#define COMMAND_LOG_PREVIEW_MAX 256

// Структура зарегистрированного обработчика
typedef struct {
    char cmd_name[NODE_COMMAND_NAME_MAX_LEN];
    node_command_handler_func_t handler;
    void *user_ctx;
    bool used;
} command_handler_entry_t;

// Кеш для защиты от дубликатов команд и идемпотентности
// ВАЖНО: Дедуп работает глобально по cmd_id (независимо от channel и топика)
// Это защищает от двойной подписки: если команда придет из temp-topic и main-topic,
// она будет обработана только один раз
// Также сохраняет final_status (DONE/ERROR) для идемпотентности
#define CMD_ID_CACHE_SIZE 128  // Минимум N=128 для идемпотентности
#define CMD_ID_TTL_MS 300000  // 5 минут TTL (увеличено для идемпотентности)
#define MAX_STATUS_LEN 16  // "DONE", "ERROR", "ACK"

typedef struct {
    char cmd_id[64];
    uint64_t timestamp_ms;
    char final_status[MAX_STATUS_LEN];  // Сохраненный финальный статус (DONE/ERROR)
    bool valid;
    bool has_final_status;  // Флаг наличия финального статуса
} cmd_id_cache_entry_t;

// Глобальный кеш для дедупа по cmd_id (независимо от channel)
// Это защищает от двойной подписки на temp и main топики
static struct {
    cmd_id_cache_entry_t global_cache[CMD_ID_CACHE_SIZE];
    size_t lru_index;  // Индекс для LRU (круговой буфер)
    SemaphoreHandle_t cache_mutex;
} s_global_cmd_cache = {0};

static struct {
    command_handler_entry_t handlers[NODE_COMMAND_HANDLER_MAX];
    size_t handler_count;
    SemaphoreHandle_t mutex;
} s_command_handler = {0};

static void init_mutexes(void) {
    if (s_command_handler.mutex == NULL) {
        s_command_handler.mutex = xSemaphoreCreateMutex();
    }
    if (s_global_cmd_cache.cache_mutex == NULL) {
        s_global_cmd_cache.cache_mutex = xSemaphoreCreateMutex();
    }
}

static const char *normalize_response_status(const char *status) {
    if (status == NULL) {
        return "ERROR";
    }

    if (strcmp(status, "ACK") == 0 ||
        strcmp(status, "DONE") == 0 ||
        strcmp(status, "ERROR") == 0 ||
        strcmp(status, "INVALID") == 0 ||
        strcmp(status, "BUSY") == 0 ||
        strcmp(status, "NO_EFFECT") == 0) {
        return status;
    }

    ESP_LOGW(TAG, "Non-canonical command_response status '%s', forcing ERROR", status);
    return "ERROR";
}

static void log_command_response_summary(
    const char *cmd,
    const char *cmd_id,
    const char *channel,
    const cJSON *response
) {
    if (!response) {
        return;
    }

    const cJSON *status_item = cJSON_GetObjectItem((cJSON *)response, "status");
    const cJSON *error_code_item = cJSON_GetObjectItem((cJSON *)response, "error_code");

    const char *status = cJSON_IsString(status_item) ? status_item->valuestring : "UNKNOWN";
    const char *error_code = cJSON_IsString(error_code_item) ? error_code_item->valuestring : NULL;

    if (error_code && error_code[0] != '\0') {
        ESP_LOGI(
            TAG,
            "Command result: cmd=%s cmd_id=%s channel=%s status=%s error_code=%s",
            cmd ? cmd : "unknown",
            cmd_id ? cmd_id : "-",
            channel ? channel : "default",
            status,
            error_code
        );
        return;
    }

    ESP_LOGI(
        TAG,
        "Command result: cmd=%s cmd_id=%s channel=%s status=%s",
        cmd ? cmd : "unknown",
        cmd_id ? cmd_id : "-",
        channel ? channel : "default",
        status
    );
}

static void build_log_preview(const char *data, int data_len, char *preview, size_t preview_size) {
    if (preview == NULL || preview_size == 0) {
        return;
    }

    preview[0] = '\0';
    if (data == NULL || data_len <= 0) {
        return;
    }

    size_t limit = preview_size - 1;
    bool truncated = false;
    if ((size_t)data_len > limit) {
        data_len = (int)limit;
        truncated = true;
    }

    memcpy(preview, data, (size_t)data_len);
    preview[data_len] = '\0';

    if (truncated && preview_size >= 4) {
        size_t len = strlen(preview);
        if (len >= 3) {
            preview[len - 3] = '.';
            preview[len - 2] = '.';
            preview[len - 1] = '.';
        }
    }
}

static bool cjson_replace_string_field(cJSON *object, const char *key, const char *value) {
    if (object == NULL || key == NULL) {
        return false;
    }

    cJSON_DeleteItemFromObject(object, key);
    if (value == NULL) {
        return true;
    }

    cJSON *item = cJSON_AddStringToObject(object, key, value);
    if (item == NULL) {
        ESP_LOGE(TAG, "Failed to add JSON string field '%s'", key);
        return false;
    }

    return true;
}

static void normalize_response_envelope(cJSON *response, const char *cmd_id) {
    if (response == NULL) {
        return;
    }

    if (cmd_id != NULL) {
        if (!cjson_replace_string_field(response, "cmd_id", cmd_id)) {
            ESP_LOGE(TAG, "Failed to normalize response cmd_id");
        }
    }

    cJSON *status_item = cJSON_GetObjectItem(response, "status");
    const char *status = cJSON_IsString(status_item) ? status_item->valuestring : NULL;
    const char *normalized_status = normalize_response_status(status);
    if (!cJSON_IsString(status_item) || normalized_status != status) {
        if (!cjson_replace_string_field(response, "status", normalized_status)) {
            ESP_LOGE(TAG, "Failed to normalize response status");
        }
    }

    cJSON *ts_item = cJSON_GetObjectItem(response, "ts");
    if (!cJSON_IsNumber(ts_item)) {
        cJSON_DeleteItemFromObject(response, "ts");
        int64_t ts_ms = node_utils_get_timestamp_seconds() * 1000;
        if (cJSON_AddNumberToObject(response, "ts", (double)ts_ms) == NULL) {
            ESP_LOGE(TAG, "Failed to normalize response timestamp");
        }
    }
}

static esp_err_t publish_command_response_json(
    const char *topic,
    const char *channel,
    const char *cmd,
    const char *cmd_id,
    cJSON *response
) {
    if (response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    normalize_response_envelope(response, cmd_id);

    char *json_str = cJSON_PrintUnformatted(response);
    if (json_str == NULL) {
        ESP_LOGE(
            TAG,
            "Failed to serialize command response: topic=%s channel=%s cmd=%s cmd_id=%s",
            topic ? topic : "-",
            channel ? channel : "default",
            cmd ? cmd : "unknown",
            cmd_id ? cmd_id : "-"
        );
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = mqtt_manager_publish_command_response(channel ? channel : "default", json_str);
    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Failed to publish command response: topic=%s channel=%s cmd=%s cmd_id=%s err=0x%x (%s)",
            topic ? topic : "-",
            channel ? channel : "default",
            cmd ? cmd : "unknown",
            cmd_id ? cmd_id : "-",
            (unsigned)err,
            esp_err_to_name(err)
        );
    }

    free(json_str);
    return err;
}

/**
 * @brief Получить node_secret из конфигурации
 *
 * @param secret_out Буфер для секрета
 * @param secret_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
static esp_err_t get_node_secret(char *secret_out, size_t secret_size) {
    if (!secret_out || secret_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Пытаемся получить секрет из конфигурации
    char *json_buf = (char *)malloc(CONFIG_STORAGE_MAX_JSON_SIZE);
    if (!json_buf) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t result = ESP_ERR_NOT_FOUND;
    if (config_storage_get_json(json_buf, CONFIG_STORAGE_MAX_JSON_SIZE) == ESP_OK) {
        cJSON *config = cJSON_Parse(json_buf);
        if (config) {
            cJSON *secret_item = cJSON_GetObjectItem(config, "node_secret");
            if (cJSON_IsString(secret_item) && secret_item->valuestring) {
                strncpy(secret_out, secret_item->valuestring, secret_size - 1);
                secret_out[secret_size - 1] = '\0';
                cJSON_Delete(config);
                result = ESP_OK;
                free(json_buf);
                return result;
            }
            cJSON_Delete(config);
        }
    }

    free(json_buf);
    return result;
}

/**
 * @brief Проверить, разрешен ли legacy режим без HMAC
 */
static bool get_allow_legacy_hmac(void) {
    char *json_buf = (char *)malloc(CONFIG_STORAGE_MAX_JSON_SIZE);
    if (!json_buf) {
        return false;
    }

    bool allow = false;
    if (config_storage_get_json(json_buf, CONFIG_STORAGE_MAX_JSON_SIZE) == ESP_OK) {
        cJSON *config = cJSON_Parse(json_buf);
        if (config) {
            cJSON *flag = cJSON_GetObjectItem(config, "allow_legacy_hmac");
            allow = (flag != NULL && cJSON_IsBool(flag) && cJSON_IsTrue(flag));
            cJSON_Delete(config);
        }
    }
    free(json_buf);
    return allow;
}

/**
 * @brief Вычислить HMAC-SHA256 подпись
 * 
 * @param secret Секретный ключ
 * @param message Сообщение для подписи
 * @param message_len Длина сообщения
 * @param signature_out Буфер для подписи (64 символа hex)
 * @param signature_size Размер буфера (должен быть >= 65)
 * @return esp_err_t ESP_OK при успехе
 */
static esp_err_t compute_hmac_sha256(const char *secret, const uint8_t *message, size_t message_len,
                                     char *signature_out, size_t signature_size) {
    if (!secret || !message || !signature_out || signature_size < 65) {
        return ESP_ERR_INVALID_ARG;
    }
    
    const mbedtls_md_info_t *md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!md_info) {
        ESP_LOGE(TAG, "Failed to get MD info for SHA256");
        return ESP_FAIL;
    }
    
    mbedtls_md_context_t ctx;
    mbedtls_md_init(&ctx);
    
    if (mbedtls_md_setup(&ctx, md_info, 1) != 0) {  // 1 = HMAC mode
        ESP_LOGE(TAG, "Failed to setup MD context");
        mbedtls_md_free(&ctx);
        return ESP_FAIL;
    }
    
    if (mbedtls_md_hmac_starts(&ctx, (const unsigned char *)secret, strlen(secret)) != 0) {
        ESP_LOGE(TAG, "Failed to start HMAC");
        mbedtls_md_free(&ctx);
        return ESP_FAIL;
    }
    
    if (mbedtls_md_hmac_update(&ctx, message, message_len) != 0) {
        ESP_LOGE(TAG, "Failed to update HMAC");
        mbedtls_md_free(&ctx);
        return ESP_FAIL;
    }
    
    unsigned char hmac[32];
    if (mbedtls_md_hmac_finish(&ctx, hmac) != 0) {
        ESP_LOGE(TAG, "Failed to finish HMAC");
        mbedtls_md_free(&ctx);
        return ESP_FAIL;
    }
    
    mbedtls_md_free(&ctx);
    
    // Конвертируем в hex строку
    for (size_t i = 0; i < 32; i++) {
        snprintf(signature_out + (i * 2), 3, "%02x", hmac[i]);
    }
    signature_out[64] = '\0';
    
    return ESP_OK;
}

/**
 * @brief Проверить HMAC подпись команды
 * 
 * @param cmd Команда
 * @param ts Timestamp (секунды)
 * @param sig Подпись (hex строка)
 * @return true если подпись валидна
 */
typedef struct {
    const char *key;
    const cJSON *value;
} json_kv_t;

static int compare_json_kv(const void *a, const void *b) {
    const json_kv_t *item_a = (const json_kv_t *)a;
    const json_kv_t *item_b = (const json_kv_t *)b;

    if (item_a->key == NULL && item_b->key == NULL) {
        return 0;
    }
    if (item_a->key == NULL) {
        return -1;
    }
    if (item_b->key == NULL) {
        return 1;
    }
    return strcmp(item_a->key, item_b->key);
}

static cJSON *canonicalize_json(const cJSON *input) {
    if (input == NULL) {
        return NULL;
    }

    if (cJSON_IsObject(input)) {
        cJSON *out = cJSON_CreateObject();
        if (!out) {
            return NULL;
        }

        size_t count = 0;
        for (const cJSON *child = input->child; child; child = child->next) {
            count++;
        }

        if (count == 0) {
            return out;
        }

        json_kv_t *items = (json_kv_t *)calloc(count, sizeof(json_kv_t));
        if (!items) {
            cJSON_Delete(out);
            return NULL;
        }

        size_t idx = 0;
        for (const cJSON *child = input->child; child; child = child->next) {
            items[idx].key = child->string;
            items[idx].value = child;
            idx++;
        }

        qsort(items, count, sizeof(json_kv_t), compare_json_kv);

        for (size_t i = 0; i < count; i++) {
            cJSON *child_value = canonicalize_json(items[i].value);
            if (!child_value) {
                free(items);
                cJSON_Delete(out);
                return NULL;
            }
            cJSON_AddItemToObject(out, items[i].key ? items[i].key : "", child_value);
        }

        free(items);
        return out;
    }

    if (cJSON_IsArray(input)) {
        cJSON *out = cJSON_CreateArray();
        if (!out) {
            return NULL;
        }

        for (const cJSON *child = input->child; child; child = child->next) {
            cJSON *child_value = canonicalize_json(child);
            if (!child_value) {
                cJSON_Delete(out);
                return NULL;
            }
            cJSON_AddItemToArray(out, child_value);
        }

        return out;
    }

    return cJSON_Duplicate(input, 1);
}

static esp_err_t compute_command_signature(const cJSON *json, char *signature_out, size_t signature_size) {
    if (!json || !signature_out || signature_size < 65) {
        return ESP_ERR_INVALID_ARG;
    }

    char secret[128];
    if (get_node_secret(secret, sizeof(secret)) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get node_secret");
        return ESP_ERR_NOT_FOUND;
    }

    cJSON *sanitized = cJSON_Duplicate(json, 1);
    if (!sanitized) {
        return ESP_ERR_NO_MEM;
    }

    cJSON_DeleteItemFromObject(sanitized, "sig");

    cJSON *canonical = canonicalize_json(sanitized);
    cJSON_Delete(sanitized);
    if (!canonical) {
        return ESP_ERR_NO_MEM;
    }

    char *payload = cJSON_PrintUnformatted(canonical);
    cJSON_Delete(canonical);
    if (!payload) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = compute_hmac_sha256(secret,
                                        (const uint8_t *)payload,
                                        strlen(payload),
                                        signature_out,
                                        signature_size);
    free(payload);
    return err;
}

static bool verify_command_signature(const cJSON *json,
                                     const char *cmd,
                                     int64_t ts,
                                     const char *sig,
                                     bool allow_legacy_sig) {
    if (!json || !cmd || !sig) {
        ESP_LOGE(TAG, "Invalid parameters for signature verification");
        return false;
    }
    
    // Проверка длины команды (защита от переполнения)
    size_t cmd_len = strlen(cmd);
    if (cmd_len == 0 || cmd_len > NODE_COMMAND_NAME_MAX_LEN) {
        ESP_LOGE(TAG, "Invalid command length: %zu (max: %d)", cmd_len, NODE_COMMAND_NAME_MAX_LEN);
        return false;
    }

    char expected_sig[65];
    if (compute_command_signature(json, expected_sig, sizeof(expected_sig)) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to compute canonical HMAC");
        return false;
    }

    // Сравниваем подписи (константное время, регистронезависимое сравнение hex)
    bool is_valid = (strlen(sig) == 64 && strlen(expected_sig) == 64);
    if (is_valid) {
        for (size_t i = 0; i < 64; i++) {
            // Нормализуем к нижнему регистру для сравнения (hex всегда в нижнем регистре)
            char sig_char = (sig[i] >= 'A' && sig[i] <= 'F') ? (sig[i] - 'A' + 'a') : sig[i];
            char expected_char = expected_sig[i];  // expected_sig уже в нижнем регистре
            if (sig_char != expected_char) {
                is_valid = false;
                break;
            }
        }
    }
    
    if (!is_valid) {
        ESP_LOGW(TAG, "Command signature verification failed: cmd=%s, ts=%lld", cmd, (long long)ts);
        ESP_LOGD(TAG, "Expected sig: %s", expected_sig);
        ESP_LOGD(TAG, "Received sig: %s", sig);
    }

    if (!is_valid && allow_legacy_sig) {
        char secret[128];
        if (get_node_secret(secret, sizeof(secret)) != ESP_OK) {
            return false;
        }

        char legacy_payload[256];
        int legacy_len = snprintf(legacy_payload, sizeof(legacy_payload), "%s|%lld",
                                  cmd, (long long)ts);
        if (legacy_len <= 0 || legacy_len >= (int)sizeof(legacy_payload)) {
            return false;
        }

        char legacy_expected[65];
        if (compute_hmac_sha256(secret,
                                (const uint8_t *)legacy_payload,
                                legacy_len,
                                legacy_expected,
                                sizeof(legacy_expected)) != ESP_OK) {
            return false;
        }

        bool legacy_valid = (strlen(sig) == 64);
        if (legacy_valid) {
            for (size_t i = 0; i < 64; i++) {
                char sig_char = (sig[i] >= 'A' && sig[i] <= 'F') ? (sig[i] - 'A' + 'a') : sig[i];
                char expected_char = legacy_expected[i];
                if (sig_char != expected_char) {
                    legacy_valid = false;
                    break;
                }
            }
        }

        if (legacy_valid) {
            ESP_LOGW(TAG, "Command accepted with legacy HMAC signature: cmd=%s", cmd);
            return true;
        }
    }

    return is_valid;
}

/**
 * @brief Проверить timestamp команды
 * 
 * @param ts Timestamp команды (секунды)
 * @return true если timestamp валиден
 */
static bool verify_command_timestamp(int64_t ts) {
    int64_t now = node_utils_get_timestamp_seconds();
    int64_t diff = (now > ts) ? (now - ts) : (ts - now);
    
    if (diff > HMAC_TIMESTAMP_TOLERANCE_SEC) {
        ESP_LOGW(TAG, "Command timestamp expired: ts=%lld, now=%lld, diff=%lld", 
                 (long long)ts, (long long)now, (long long)diff);
        return false;
    }
    
    return true;
}

esp_err_t node_command_handler_register(
    const char *cmd_name,
    node_command_handler_func_t handler,
    void *user_ctx
) {
    if (cmd_name == NULL || handler == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    init_mutexes();

    if (s_command_handler.mutex == NULL) {
        return ESP_ERR_NO_MEM;
    }

    if (xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Проверяем, не зарегистрирована ли уже команда (по всему массиву)
        for (size_t i = 0; i < NODE_COMMAND_HANDLER_MAX; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd_name) == 0) {
                xSemaphoreGive(s_command_handler.mutex);
                ESP_LOGW(TAG, "Command %s already registered", cmd_name);
                return ESP_ERR_INVALID_STATE;
            }
        }

        // Ищем свободный слот по всему массиву
        for (size_t i = 0; i < NODE_COMMAND_HANDLER_MAX; i++) {
            if (!s_command_handler.handlers[i].used) {
                // Найден свободный слот
                strncpy(s_command_handler.handlers[i].cmd_name, cmd_name, NODE_COMMAND_NAME_MAX_LEN - 1);
                s_command_handler.handlers[i].cmd_name[NODE_COMMAND_NAME_MAX_LEN - 1] = '\0';
                s_command_handler.handlers[i].handler = handler;
                s_command_handler.handlers[i].user_ctx = user_ctx;
                s_command_handler.handlers[i].used = true;
                
                // Обновляем handler_count для оптимизации поиска при следующей регистрации
                if (i >= s_command_handler.handler_count) {
                    s_command_handler.handler_count = i + 1;
                }
                
                xSemaphoreGive(s_command_handler.mutex);
                ESP_LOGI(TAG, "Command handler registered: %s", cmd_name);
                return ESP_OK;
            }
        }
        
        xSemaphoreGive(s_command_handler.mutex);
        ESP_LOGE(TAG, "Command handler registry is full");
        return ESP_ERR_NO_MEM;
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t node_command_handler_unregister(const char *cmd_name) {
    if (cmd_name == NULL || s_command_handler.mutex == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Ищем обработчик по всему массиву, не только до handler_count
        // чтобы не пропустить обработчики после удаления других
        for (size_t i = 0; i < NODE_COMMAND_HANDLER_MAX; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd_name) == 0) {
                s_command_handler.handlers[i].used = false;
                memset(&s_command_handler.handlers[i], 0, sizeof(command_handler_entry_t));
                // НЕ уменьшаем handler_count - он используется только для поиска свободного слота
                // при регистрации, а при поиске обработчика проверяем used флаг
                xSemaphoreGive(s_command_handler.mutex);
                ESP_LOGI(TAG, "Command handler unregistered: %s", cmd_name);
                return ESP_OK;
            }
        }
        xSemaphoreGive(s_command_handler.mutex);
    }

    return ESP_ERR_NOT_FOUND;
}

void node_command_handler_process(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    (void)user_ctx;
    
    if (data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid command parameters: topic=%s channel=%s data_len=%d",
                 topic ? topic : "-",
                 channel ? channel : "default",
                 data_len);
        return;
    }

    if (data_len > NODE_COMMAND_MAX_JSON_SIZE) {
        ESP_LOGE(TAG, "Command payload too large: topic=%s channel=%s len=%d max=%d",
                 topic ? topic : "-",
                 channel ? channel : "default",
                 data_len,
                 NODE_COMMAND_MAX_JSON_SIZE);
        return;
    }

    // Парсинг JSON команды
    cJSON *json = cJSON_ParseWithLength(data, data_len);
    if (!json) {
        char preview[COMMAND_LOG_PREVIEW_MAX];
        build_log_preview(data, data_len, preview, sizeof(preview));
        ESP_LOGE(TAG, "Failed to parse command JSON: topic=%s channel=%s len=%d payload=%s",
                 topic ? topic : "-",
                 channel ? channel : "default",
                 data_len,
                 preview);
        return;
    }

    if (!cJSON_IsObject(json)) {
        ESP_LOGE(TAG, "Invalid command format: root JSON must be an object");
        cJSON_Delete(json);
        return;
    }

    // Извлечение cmd и cmd_id
    cJSON *cmd_item = cJSON_GetObjectItem(json, "cmd");
    cJSON *cmd_id_item = cJSON_GetObjectItem(json, "cmd_id");

    const char *cmd = cJSON_IsString(cmd_item) ? cmd_item->valuestring : NULL;
    const char *cmd_id = cJSON_IsString(cmd_id_item) ? cmd_id_item->valuestring : NULL;

    if (cmd == NULL || cmd[0] == '\0' || cmd_id == NULL || cmd_id[0] == '\0') {
        ESP_LOGE(TAG, "Invalid command format: missing or invalid cmd/cmd_id");
        if (cmd_id != NULL) {
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "invalid_command_format",
                "Command must include non-empty cmd and cmd_id",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
        }
        cJSON_Delete(json);
        return;
    }

    if (strlen(cmd) >= NODE_COMMAND_NAME_MAX_LEN) {
        ESP_LOGE(TAG, "Command name too long: topic=%s channel=%s cmd_id=%s len=%zu max=%d",
                 topic ? topic : "-",
                 channel ? channel : "default",
                 cmd_id,
                 strlen(cmd),
                 NODE_COMMAND_NAME_MAX_LEN - 1);
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_command_format",
            "Command name is too long",
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    if (strlen(cmd_id) >= sizeof(s_global_cmd_cache.global_cache[0].cmd_id)) {
        ESP_LOGE(TAG, "cmd_id too long: topic=%s channel=%s cmd=%s len=%zu max=%zu",
                 topic ? topic : "-",
                 channel ? channel : "default",
                 cmd,
                 strlen(cmd_id),
                 sizeof(s_global_cmd_cache.global_cache[0].cmd_id) - 1);
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_command_format",
            "cmd_id is too long",
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    // Извлечение ts и sig для HMAC проверки (опциональные поля для обратной совместимости)
    cJSON *ts_item = cJSON_GetObjectItem(json, "ts");
    cJSON *sig_item = cJSON_GetObjectItem(json, "sig");
    
    bool has_ts = (ts_item != NULL);
    bool has_sig = (sig_item != NULL);
    bool has_hmac_fields = (has_ts && has_sig);
    bool allow_legacy_hmac = get_allow_legacy_hmac();
    bool invalid_hmac_fields = (has_ts != has_sig);

    if (invalid_hmac_fields) {
        ESP_LOGE(TAG, "Invalid HMAC fields: ts and sig must be provided together");
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_hmac_format",
            "ts and sig must be provided together",
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    if (!has_hmac_fields && !allow_legacy_hmac) {
        ESP_LOGW(TAG, "Command rejected without HMAC fields: cmd=%s, cmd_id=%s", cmd, cmd_id);
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "hmac_required",
            "Command must include ts and sig",
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }
    
    // Если есть поля ts и sig, проверяем HMAC подпись
    if (has_hmac_fields) {
        if (!cJSON_IsNumber(ts_item) || !cJSON_IsString(sig_item) || !sig_item->valuestring) {
            ESP_LOGE(TAG, "Invalid HMAC fields format: ts must be number, sig must be non-null string");
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "invalid_hmac_format",
                "Invalid HMAC fields format",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        int64_t ts = (int64_t)cJSON_GetNumberValue(ts_item);
        const char *sig = sig_item->valuestring;

        char secret_probe[128];
        if (get_node_secret(secret_probe, sizeof(secret_probe)) != ESP_OK) {
            ESP_LOGE(TAG, "Missing node_secret for HMAC verification");
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "missing_node_secret",
                "node_secret is not configured",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        // Проверка длины подписи (должна быть 64 символа hex)
        if (strlen(sig) != 64) {
            ESP_LOGE(TAG, "Invalid HMAC signature length: expected 64, got %zu", strlen(sig));
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "invalid_hmac_format",
                "Invalid HMAC signature length",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        bool time_synced = node_utils_is_time_synced();
        if (!time_synced && strcmp(cmd, "set_time") != 0) {
            ESP_LOGW(TAG, "Command rejected: time not synchronized (cmd=%s, cmd_id=%s)", cmd, cmd_id);
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "time_not_synced",
                "Time is not synchronized yet",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }

        if (time_synced && !verify_command_timestamp(ts)) {
            ESP_LOGW(TAG, "Command timestamp verification failed: cmd=%s, cmd_id=%s", cmd, cmd_id);
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "timestamp_expired",
                "Command timestamp is outside acceptable range",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        // Проверка HMAC подписи
        if (!verify_command_signature(json, cmd, ts, sig, allow_legacy_hmac)) {
            ESP_LOGW(TAG, "Command HMAC signature verification failed: cmd=%s, cmd_id=%s", cmd, cmd_id);
            cJSON *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "invalid_signature",
                "Command HMAC signature verification failed",
                NULL
            );
            if (response) {
                (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        ESP_LOGI(TAG, "Command HMAC signature verified: cmd=%s, cmd_id=%s", cmd, cmd_id);
    } else {
        // Legacy режим: допускаем команды без ts/sig, но не спамим лог
        if (!g_logged_missing_hmac) {
            ESP_LOGW(TAG, "Command without HMAC fields (ts/sig): cmd=%s, cmd_id=%s (legacy mode)", cmd, cmd_id);
            g_logged_missing_hmac = true;
        }
    }

    // Проверка на дубликат и идемпотентность
    const char *cached_status = node_command_handler_get_cached_status(cmd_id, channel);
    if (cached_status != NULL) {
        // Команда уже обработана - возвращаем сохраненный финальный статус (DONE/ERROR)
        ESP_LOGI(TAG, "Idempotent command: %s (id: %s, channel: %s) - returning cached status: %s", 
                 cmd, cmd_id, channel ? channel : "default", cached_status);
        
        // Определяем статус ответа на основе cached_status
        const char *response_status = "DONE";
        const char *error_code = NULL;
        const char *error_message = NULL;
        
        if (strcmp(cached_status, IN_PROGRESS_STATUS) == 0) {
            response_status = "ACK";
        } else if (strcmp(cached_status, "DONE") == 0) {
            response_status = "DONE";
        } else if (strcmp(cached_status, "ERROR") == 0) {
            response_status = "ERROR";
            error_code = "command_already_failed";
            error_message = "Command was already processed and failed previously";
        }
        
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            response_status,
            error_code,
            error_message,
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    ESP_LOGI(TAG, "Processing command: %s (id: %s) on channel: %s", cmd, cmd_id, channel ? channel : "default");

    // Проверка safe_mode: блокируем все команды кроме exit_safe_mode
    if (node_framework_is_safe_mode() && strcmp(cmd, "exit_safe_mode") != 0) {
        ESP_LOGW(TAG, "Command %s rejected: node is in safe_mode", cmd);
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "safe_mode_active",
            "Node is in safe mode. Use 'exit_safe_mode' command to exit.",
            NULL
        );
        if (response) {
            (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    // Поиск обработчика
    init_mutexes();
    node_command_handler_func_t handler = NULL;
    void *handler_ctx = NULL;

    if (s_command_handler.mutex &&
        xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Поиск по всему массиву, проверяя used флаг
        for (size_t i = 0; i < NODE_COMMAND_HANDLER_MAX; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd) == 0) {
                handler = s_command_handler.handlers[i].handler;
                handler_ctx = s_command_handler.handlers[i].user_ctx;
                break;
            }
        }
        xSemaphoreGive(s_command_handler.mutex);
    }

    // Обработка команды
    cJSON *response = NULL;
    esp_err_t err = ESP_ERR_NOT_FOUND;

    if (handler) {
        // Извлекаем параметры команды. Новый формат: {"cmd": "...", "cmd_id": "...", "params": {...}}
        // Старый формат: поля команды на корне. Поддерживаем оба.
        cJSON *params_obj = cJSON_GetObjectItem(json, "params");
        cJSON *params = NULL;

        if (params_obj != NULL && !cJSON_IsObject(params_obj)) {
            ESP_LOGE(TAG, "Invalid command format: params must be an object");
            response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "invalid_params_format",
                "params must be a JSON object",
                NULL
            );
        } else if (params_obj && cJSON_IsObject(params_obj)) {
            params = cJSON_Duplicate(params_obj, 1);
            // Добавляем cmd_id в params для обработчиков (нужно для командного автомата)
            if (params && cmd_id) {
                if (!cjson_replace_string_field(params, "cmd_id", cmd_id)) {
                    cJSON_Delete(params);
                    params = NULL;
                }
            }
        } else {
            // Fallback на старый формат: копируем весь объект и убираем служебные поля
            params = cJSON_Duplicate(json, 1);
            if (params) {
                cJSON_DeleteItemFromObject(params, "cmd");
                cJSON_DeleteItemFromObject(params, "ts");
                cJSON_DeleteItemFromObject(params, "sig");
                if (cmd_id && !cjson_replace_string_field(params, "cmd_id", cmd_id)) {
                    cJSON_Delete(params);
                    params = NULL;
                }
            }
        }

        if (params == NULL && response == NULL) {
            ESP_LOGE(TAG, "Failed to duplicate command params (out of memory)");
            response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "memory_error",
                "Failed to parse command parameters",
                NULL
            );
        } else {
            err = handler(channel, params, &response, handler_ctx);
            
            // Если обработчик не создал ответ, создаем его здесь
            if (err == ESP_OK && response == NULL) {
                response = node_command_handler_create_response(
                    cmd_id,
                    "DONE",
                    NULL,
                    NULL,
                    NULL
                );
            } else if (err != ESP_OK && response == NULL) {
                response = node_command_handler_create_response(
                    cmd_id,
                    "ERROR",
                    "handler_error",
                    "Command handler failed",
                    NULL
                );
            }
            
            // Убеждаемся, что cmd_id есть в ответе (если ответ был создан)
            if (response != NULL) {
                normalize_response_envelope(response, cmd_id);
            }
            
            cJSON_Delete(params);
        }

        // Уведомляем OLED о принятой команде
        oled_ui_notify_command();
    } else {
        ESP_LOGW(TAG, "Unknown command: %s", cmd);
        response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "unknown_command",
            "Command not found",
            NULL
        );
    }

    // Публикация ответа
    if (response) {
        normalize_response_envelope(response, cmd_id);

        // Извлекаем финальный статус из ответа для сохранения в кеш
        cJSON *status_item = cJSON_GetObjectItem(response, "status");
        if (status_item && cJSON_IsString(status_item)) {
            const char *status_str = status_item->valuestring;
            // Сохраняем только терминальные статусы (DONE/ERROR)
            if (strcmp(status_str, "DONE") == 0 || 
                strcmp(status_str, "ERROR") == 0) {
                node_command_handler_cache_final_status(cmd_id, channel, status_str);
            }
        }
        
        (void)publish_command_response_json(topic, channel, cmd, cmd_id, response);
        log_command_response_summary(cmd, cmd_id, channel, response);
        cJSON_Delete(response);
    }

    cJSON_Delete(json);
}

const char *node_command_handler_get_cmd_id(const cJSON *params) {
    if (!params) {
        return NULL;
    }

    cJSON *cmd_id_item = cJSON_GetObjectItem(params, "cmd_id");
    if (cmd_id_item && cJSON_IsString(cmd_id_item)) {
        return cmd_id_item->valuestring;
    }

    return NULL;
}

esp_err_t node_command_handler_publish_accepted(const char *cmd_id, const char *channel) {
    if (!cmd_id) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *publish_channel = channel ? channel : "default";
    cJSON *accepted_response = node_command_handler_create_response(cmd_id, "ACK", NULL, NULL, NULL);
    if (!accepted_response) {
        return ESP_ERR_NO_MEM;
    }

    char *json_str = cJSON_PrintUnformatted(accepted_response);
    if (json_str) {
        esp_err_t publish_err = mqtt_manager_publish_command_response(publish_channel, json_str);
        if (publish_err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "Failed to publish ACK response: cmd_id=%s channel=%s err=0x%x (%s)",
                cmd_id,
                publish_channel,
                (unsigned)publish_err,
                esp_err_to_name(publish_err)
            );
        }
        free(json_str);
    } else {
        ESP_LOGE(TAG, "Failed to serialize ACK response: cmd_id=%s channel=%s", cmd_id, publish_channel);
    }
    cJSON_Delete(accepted_response);

    return ESP_OK;
}

/**
 * @brief Обработчик команды set_time
 * 
 * Устанавливает время на ноде через смещение.
 * Формат команды:
 * {
 *   "cmd": "set_time",
 *   "cmd_id": "<uuid>",
 *   "unix_ts": 1717770000,
 *   "source": "server"
 * }
 */
static esp_err_t handle_set_time(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)user_ctx;
    
    if (params == NULL) {
        if (response) {
            *response = node_command_handler_create_response(
                NULL,
                "ERROR",
                "invalid_params",
                "Missing parameters",
                NULL
            );
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    // Извлекаем unix_ts
    cJSON *unix_ts_item = cJSON_GetObjectItem(params, "unix_ts");
    if (!cJSON_IsNumber(unix_ts_item)) {
        if (response) {
            *response = node_command_handler_create_response(
                NULL,
                "ERROR",
                "invalid_params",
                "Missing or invalid unix_ts",
                NULL
            );
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    int64_t unix_ts = (int64_t)cJSON_GetNumberValue(unix_ts_item);
    esp_err_t err = node_utils_set_time(unix_ts);
    
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Time set successfully: %lld", (long long)unix_ts);
        if (response) {
            *response = node_command_handler_create_response(
                NULL,
                "DONE",
                NULL,
                NULL,
                NULL
            );
        }
        return ESP_OK;
    } else {
        ESP_LOGE(TAG, "Failed to set time: %s", esp_err_to_name(err));
        if (response) {
            *response = node_command_handler_create_response(
                NULL,
                "ERROR",
                "set_time_failed",
                "Failed to set time",
                NULL
            );
        }
        return err;
    }
}

static void restart_timer_cb(void *arg) {
    (void)arg;
    ESP_LOGW(TAG, "Restarting device by command");
    esp_restart();
}

static esp_err_t schedule_restart_timer(void) {
    if (!s_restart_timer) {
        const esp_timer_create_args_t args = {
            .callback = restart_timer_cb,
            .arg = NULL,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "cmd_restart"
        };
        esp_err_t err = esp_timer_create(&args, &s_restart_timer);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to create restart timer: %s", esp_err_to_name(err));
            return err;
        }
    }

    esp_timer_stop(s_restart_timer);
    return esp_timer_start_once(s_restart_timer, 1000 * 1000);
}

static esp_err_t handle_restart(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)params;
    (void)user_ctx;

    esp_err_t err = schedule_restart_timer();
    if (err != ESP_OK) {
        if (response) {
            *response = node_command_handler_create_response(
                NULL,
                "ERROR",
                "restart_schedule_failed",
                "Failed to schedule restart",
                NULL
            );
        }
        return err;
    }

    if (response) {
        *response = node_command_handler_create_response(
            NULL,
            "DONE",
            NULL,
            NULL,
            NULL
        );
    }
    return ESP_OK;
}

static esp_err_t handle_publish_config_report(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)user_ctx;
    const char *cmd_id = params ? node_command_handler_get_cmd_id(params) : NULL;

    esp_err_t err = node_utils_publish_config_report();
    if (err != ESP_OK) {
        if (response) {
            *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "config_report_failed",
                "Failed to publish config_report",
                NULL
            );
        }
        return err;
    }

    if (response) {
        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddStringToObject(extra, "note", "config_report_published");
        }
        *response = node_command_handler_create_response(
            cmd_id,
            "DONE",
            NULL,
            NULL,
            extra
        );
        if (extra) {
            cJSON_Delete(extra);
        }
    }

    return ESP_OK;
}

/**
 * @brief Инициализация встроенных обработчиков команд
 * 
 * Регистрирует системные команды, такие как set_time
 */
void node_command_handler_init_builtin_handlers(void) {
    node_command_handler_register("set_time", handle_set_time, NULL);
    node_command_handler_register("restart", handle_restart, NULL);
    node_command_handler_register("reboot", handle_restart, NULL);
    node_command_handler_register("report_config", handle_publish_config_report, NULL);
    node_command_handler_register("config_report", handle_publish_config_report, NULL);
    node_command_handler_register("get_config", handle_publish_config_report, NULL);
    node_command_handler_register("sync_config", handle_publish_config_report, NULL);
    ESP_LOGD(TAG, "Built-in command handlers registered");
}

cJSON *node_command_handler_create_response(
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *error_message,
    const cJSON *extra_data
) {
    cJSON *response = cJSON_CreateObject();
    if (!response) {
        return NULL;
    }

    if (cmd_id && cJSON_AddStringToObject(response, "cmd_id", cmd_id) == NULL) {
        ESP_LOGE(TAG, "Failed to add response cmd_id");
        cJSON_Delete(response);
        return NULL;
    }

    const char *normalized_status = normalize_response_status(status);
    if (cJSON_AddStringToObject(response, "status", normalized_status) == NULL) {
        ESP_LOGE(TAG, "Failed to add response status");
        cJSON_Delete(response);
        return NULL;
    }

    // ts в миллисекундах согласно эталону node-sim
    int64_t ts_ms = node_utils_get_timestamp_seconds() * 1000;
    if (cJSON_AddNumberToObject(response, "ts", (double)ts_ms) == NULL) {
        ESP_LOGE(TAG, "Failed to add response timestamp");
        cJSON_Delete(response);
        return NULL;
    }

    if (error_code && strcmp(normalized_status, "ERROR") == 0) {
        if (cJSON_AddStringToObject(response, "error_code", error_code) == NULL) {
            ESP_LOGE(TAG, "Failed to add response error_code");
            cJSON_Delete(response);
            return NULL;
        }
    }

    if (error_message && strcmp(normalized_status, "ERROR") == 0) {
        if (cJSON_AddStringToObject(response, "error_message", error_message) == NULL) {
            ESP_LOGE(TAG, "Failed to add response error_message");
            cJSON_Delete(response);
            return NULL;
        }
    }

    if (extra_data) {
        cJSON *details = cJSON_Duplicate(extra_data, 1);
        if (details == NULL) {
            ESP_LOGE(TAG, "Failed to duplicate response details");
            cJSON_Delete(response);
            return NULL;
        }
        if (!cJSON_AddItemToObject(response, "details", details)) {
            ESP_LOGE(TAG, "Failed to add response details");
            cJSON_Delete(details);
            cJSON_Delete(response);
            return NULL;
        }
    }

    return response;
}

bool node_command_handler_is_duplicate(const char *cmd_id, const char *channel) {
    // Используем get_cached_status для проверки дубликатов
    return (node_command_handler_get_cached_status(cmd_id, channel) != NULL);
}

/**
 * @brief Получить сохраненный финальный статус команды из кеша
 * 
 * @param cmd_id ID команды
 * @param channel Имя канала (может быть NULL)
 * @return Указатель на строку статуса, IN_PROGRESS если команда уже в обработке, или NULL если команда не найдена
 */
const char *node_command_handler_get_cached_status(const char *cmd_id, const char *channel) {
    (void)channel;  // Не используем channel для глобального кеша
    
    if (cmd_id == NULL) {
        return NULL;
    }

    init_mutexes();

    if (s_global_cmd_cache.cache_mutex == NULL) {
        return NULL;
    }

    uint64_t current_time_ms = esp_timer_get_time() / 1000;
    const char *cached_status = NULL;

    // ГЛОБАЛЬНЫЙ ДЕДУП: проверяем cmd_id независимо от channel и топика
    // Это защищает от двойной подписки: если команда придет из temp-topic и main-topic,
    // она будет обработана только один раз
    if (xSemaphoreTake(s_global_cmd_cache.cache_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Проверяем глобальный кеш
        for (size_t i = 0; i < CMD_ID_CACHE_SIZE; i++) {
            if (s_global_cmd_cache.global_cache[i].valid) {
                // Проверяем TTL
                if (current_time_ms - s_global_cmd_cache.global_cache[i].timestamp_ms > CMD_ID_TTL_MS) {
                    s_global_cmd_cache.global_cache[i].valid = false;
                    s_global_cmd_cache.global_cache[i].has_final_status = false;
                    continue;
                }

                // Проверяем совпадение cmd_id (глобально, независимо от channel)
                if (strcmp(s_global_cmd_cache.global_cache[i].cmd_id, cmd_id) == 0) {
                    // Если есть финальный статус, возвращаем его
                    if (s_global_cmd_cache.global_cache[i].has_final_status) {
                        cached_status = s_global_cmd_cache.global_cache[i].final_status;
                    } else {
                        // Команда уже в обработке - не выполняем повторно
                        cached_status = IN_PROGRESS_STATUS;
                        s_global_cmd_cache.global_cache[i].timestamp_ms = current_time_ms;
                    }
                    xSemaphoreGive(s_global_cmd_cache.cache_mutex);
                    if (cached_status) {
                        ESP_LOGD(TAG, "Cached final status found: cmd_id=%s, status=%s", cmd_id, cached_status);
                    }
                    return cached_status;
                }
            }
        }

        // Команда не найдена - добавляем в глобальный кеш (LRU: перезаписываем старую запись)
        size_t idx = s_global_cmd_cache.lru_index % CMD_ID_CACHE_SIZE;
        strncpy(s_global_cmd_cache.global_cache[idx].cmd_id, cmd_id, 63);
        s_global_cmd_cache.global_cache[idx].cmd_id[63] = '\0';
        s_global_cmd_cache.global_cache[idx].timestamp_ms = current_time_ms;
        s_global_cmd_cache.global_cache[idx].valid = true;
        s_global_cmd_cache.global_cache[idx].has_final_status = false;
        s_global_cmd_cache.global_cache[idx].final_status[0] = '\0';
        s_global_cmd_cache.lru_index = (s_global_cmd_cache.lru_index + 1) % CMD_ID_CACHE_SIZE;

        xSemaphoreGive(s_global_cmd_cache.cache_mutex);
    }

    return NULL;
}

/**
 * @brief Сохранить финальный статус команды в кеш
 * 
 * @param cmd_id ID команды
 * @param channel Имя канала (может быть NULL)
 * @param final_status Финальный статус (DONE/ERROR)
 */
void node_command_handler_cache_final_status(const char *cmd_id, const char *channel, const char *final_status) {
    (void)channel;  // Не используем channel для глобального кеша
    
    if (cmd_id == NULL || final_status == NULL) {
        return;
    }

    const char *normalized_status = normalize_response_status(final_status);
    if (strcmp(normalized_status, "DONE") != 0 && strcmp(normalized_status, "ERROR") != 0) {
        return;
    }

    init_mutexes();

    if (s_global_cmd_cache.cache_mutex == NULL) {
        return;
    }

    // Ищем команду в кеше и обновляем финальный статус
    if (xSemaphoreTake(s_global_cmd_cache.cache_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        for (size_t i = 0; i < CMD_ID_CACHE_SIZE; i++) {
            if (s_global_cmd_cache.global_cache[i].valid &&
                strcmp(s_global_cmd_cache.global_cache[i].cmd_id, cmd_id) == 0) {
                // Найдена команда - обновляем финальный статус
                strncpy(s_global_cmd_cache.global_cache[i].final_status, normalized_status, MAX_STATUS_LEN - 1);
                s_global_cmd_cache.global_cache[i].final_status[MAX_STATUS_LEN - 1] = '\0';
                s_global_cmd_cache.global_cache[i].has_final_status = true;
                ESP_LOGI(TAG, "Cached final status for cmd_id=%s: %s", cmd_id, normalized_status);
                xSemaphoreGive(s_global_cmd_cache.cache_mutex);
                return;
            }
        }
        xSemaphoreGive(s_global_cmd_cache.cache_mutex);
    }
}
