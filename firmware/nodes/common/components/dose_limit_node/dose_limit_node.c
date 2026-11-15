#include "dose_limit_node.h"

#include "config_storage.h"
#include "node_command_handler.h"

#include "esp_log.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>

static const char *TAG = "dose_limit";
static const char *NVS_NAMESPACE = "dose_ledger";
static const char *NVS_KEY = "win";

static dose_limit_state_t s_state;
static nvs_handle_t s_nvs;
static SemaphoreHandle_t s_mutex;
static bool s_ready;
static uint8_t s_blob[DOSE_LIMIT_BLOB_MAX];
static char s_config_json[CONFIG_STORAGE_MAX_JSON_SIZE];

static bool lock_state(void)
{
    if (s_mutex == NULL) {
        return false;
    }
    return xSemaphoreTake(s_mutex, pdMS_TO_TICKS(2000)) == pdTRUE;
}

static void unlock_state(void)
{
    if (s_mutex != NULL) {
        xSemaphoreGive(s_mutex);
    }
}

static bool persist_locked(void)
{
    size_t len = 0;
    esp_err_t err;

    if (s_state.ledger_untrusted || s_nvs == 0) {
        return false;
    }
    if (!dose_limit_export(&s_state, s_blob, sizeof(s_blob), &len) || len == 0) {
        return false;
    }
    err = nvs_set_blob(s_nvs, NVS_KEY, s_blob, len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_set_blob failed: %s", esp_err_to_name(err));
        return false;
    }
    err = nvs_commit(s_nvs);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_commit failed: %s", esp_err_to_name(err));
        return false;
    }
    return true;
}

static void load_ledger_locked(void)
{
    size_t len = sizeof(s_blob);
    esp_err_t err;

    if (s_nvs != 0) {
        nvs_close(s_nvs);
        s_nvs = 0;
    }
    err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &s_nvs);
    if (err != ESP_OK) {
        s_nvs = 0;
        s_state.ledger_untrusted = true;
        ESP_LOGE(TAG, "NVS open failed, dose window treated as full: %s", esp_err_to_name(err));
        return;
    }

    err = nvs_get_blob(s_nvs, NVS_KEY, s_blob, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "Dose ledger is empty");
        return;
    }
    if (err != ESP_OK) {
        s_state.ledger_untrusted = true;
        ESP_LOGE(TAG, "NVS read failed, dose window treated as full: %s", esp_err_to_name(err));
        return;
    }
    if (!dose_limit_import(&s_state, s_blob, len)) {
        ESP_LOGE(TAG, "Dose ledger blob is corrupt, dose window treated as full");
    } else {
        ESP_LOGI(TAG, "Dose ledger restored, channels=%u", (unsigned)s_state.channel_count);
    }
}

static void bind_kind_locked(dose_limit_node_kind_t kind)
{
    if (kind == DOSE_LIMIT_NODE_PH) {
        (void)dose_limit_bind(&s_state, "pump_acid", DOSE_LIMIT_PH_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_PH_DEFAULT_DAILY_MILLI);
        (void)dose_limit_bind(&s_state, "pump_base", DOSE_LIMIT_PH_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_PH_DEFAULT_DAILY_MILLI);
        return;
    }
    (void)dose_limit_bind(&s_state, "pump_a", DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI);
    (void)dose_limit_bind(&s_state, "pump_b", DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI);
    (void)dose_limit_bind(&s_state, "pump_c", DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI);
    (void)dose_limit_bind(&s_state, "pump_d", DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI, DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI);
}

static void apply_channel_locked(const cJSON *channel)
{
    const cJSON *name_item;
    const char *canonical;
    dose_limit_channel_kind_t kind;
    const cJSON *safe;
    dose_limit_field_t per_dose;
    dose_limit_field_t daily;
    int32_t per_milli = 0;
    int32_t daily_milli = 0;
    const char *reason = NULL;

    if (!cJSON_IsObject(channel)) {
        return;
    }
    name_item = cJSON_GetObjectItemCaseSensitive(channel, "name");
    if (!cJSON_IsString(name_item) || name_item->valuestring == NULL) {
        return;
    }
    kind = dose_limit_channel_kind(name_item->valuestring);
    canonical = dose_limit_canonical_channel(name_item->valuestring);
    if (kind == DOSE_LIMIT_CHANNEL_NONE || canonical == NULL) {
        return;
    }

    safe = cJSON_GetObjectItemCaseSensitive(channel, "safe_limits");
    if (safe != NULL && !cJSON_IsObject(safe)) {
        (void)dose_limit_bind(&s_state, canonical, 0, 0);
        ESP_LOGE(TAG, "Channel %s safe_limits is not an object, doses locked", canonical);
        return;
    }

    per_dose = dose_limit_field_absent();
    daily = dose_limit_field_absent();
    if (cJSON_IsObject(safe)) {
        const cJSON *per_item = cJSON_GetObjectItemCaseSensitive(safe, "max_dose_ml");
        const cJSON *daily_item = cJSON_GetObjectItemCaseSensitive(safe, "max_daily_ml");
        if (per_item != NULL) {
            per_dose = dose_limit_field_from_number(
                true,
                cJSON_IsNumber(per_item),
                cJSON_IsNumber(per_item) ? cJSON_GetNumberValue(per_item) : 0.0
            );
        }
        if (daily_item != NULL) {
            daily = dose_limit_field_from_number(
                true,
                cJSON_IsNumber(daily_item),
                cJSON_IsNumber(daily_item) ? cJSON_GetNumberValue(daily_item) : 0.0
            );
        }
    }

    if (dose_limit_resolve_limits(kind, per_dose, daily, &per_milli, &daily_milli, &reason) != DOSE_LIMIT_CONFIG_OK) {
        (void)dose_limit_bind(&s_state, canonical, 0, 0);
        ESP_LOGE(TAG, "Channel %s dose limits rejected (%s), doses locked", canonical, reason != NULL ? reason : "rejected");
        return;
    }
    (void)dose_limit_bind(&s_state, canonical, per_milli, daily_milli);
}

esp_err_t dose_limit_node_apply_config(const cJSON *config)
{
    const cJSON *channels;
    const cJSON *channel;

    if (!cJSON_IsObject(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    channels = cJSON_GetObjectItemCaseSensitive(config, "channels");
    if (!cJSON_IsArray(channels)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!lock_state()) {
        return ESP_ERR_INVALID_STATE;
    }
    cJSON_ArrayForEach(channel, channels) {
        apply_channel_locked(channel);
    }
    unlock_state();
    return ESP_OK;
}

static void reload_stored_config(void)
{
    cJSON *config;

    if (config_storage_get_json(s_config_json, sizeof(s_config_json)) != ESP_OK) {
        return;
    }
    config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Stored NodeConfig is not JSON, keeping firmware dose defaults");
        return;
    }
    if (dose_limit_node_apply_config(config) != ESP_OK) {
        ESP_LOGW(TAG, "Stored NodeConfig has no channel array, keeping firmware dose defaults");
    }
    cJSON_Delete(config);
}

esp_err_t dose_limit_node_boot(dose_limit_node_kind_t kind)
{
    if (kind != DOSE_LIMIT_NODE_PH && kind != DOSE_LIMIT_NODE_EC) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_mutex == NULL) {
        s_mutex = xSemaphoreCreateMutex();
        if (s_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create dose limit mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    if (!lock_state()) {
        return ESP_ERR_TIMEOUT;
    }
    dose_limit_init(&s_state);
    bind_kind_locked(kind);
    load_ledger_locked();
    s_ready = true;
    unlock_state();
    reload_stored_config();
    return ESP_OK;
}

static void fill_persist_failure(const char *channel, int64_t now_sec, bool time_synced, dose_limit_result_t *out)
{
    int32_t daily_milli = 0;
    int32_t used;

    if (out == NULL) {
        return;
    }
    (void)dose_limit_channel_limits(&s_state, channel, NULL, &daily_milli);
    used = dose_limit_active_used_milli(&s_state, channel, now_sec, time_synced);
    out->pump_allowed = false;
    out->limit_milli = daily_milli;
    if (s_state.ledger_untrusted) {
        out->code = DOSE_LIMIT_DAILY;
        out->used_milli = daily_milli;
        out->remaining_milli = 0;
        return;
    }
    out->code = DOSE_LIMIT_PERSIST_FAILED;
    out->used_milli = used;
    out->remaining_milli = used < daily_milli ? daily_milli - used : 0;
}

esp_err_t dose_limit_node_reserve(
    const char *channel,
    double requested_ml,
    bool time_synced,
    int64_t now_sec,
    dose_limit_result_t *out
)
{
    dose_limit_code_t code;

    if (out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(out, 0, sizeof(*out));
    if (!lock_state()) {
        out->code = DOSE_LIMIT_UNAVAILABLE;
        out->pump_allowed = false;
        return ESP_ERR_INVALID_STATE;
    }
    if (!s_ready) {
        out->code = DOSE_LIMIT_UNAVAILABLE;
        out->pump_allowed = false;
        unlock_state();
        return ESP_ERR_INVALID_STATE;
    }

    code = dose_limit_authorize(&s_state, channel, requested_ml, now_sec, time_synced, out);
    if (code != DOSE_LIMIT_ALLOW || !out->pump_allowed) {
        out->pump_allowed = false;
        ESP_LOGW(
            TAG,
            "Dose refused channel=%s code=%s requested_ml=%.3f limit_ml=%.3f used_ml=%.3f remaining_ml=%.3f",
            channel != NULL ? channel : "-",
            dose_limit_error_code(out->code) != NULL ? dose_limit_error_code(out->code) : "-",
            dose_limit_milli_to_ml(out->requested_milli),
            dose_limit_milli_to_ml(out->limit_milli),
            dose_limit_milli_to_ml(out->used_milli),
            dose_limit_milli_to_ml(out->remaining_milli)
        );
        unlock_state();
        return ESP_ERR_INVALID_STATE;
    }

    if (!persist_locked()) {
        dose_limit_rollback(&s_state, channel, requested_ml, now_sec);
        if (!persist_locked()) {
            s_state.ledger_untrusted = true;
            ESP_LOGE(TAG, "Dose ledger persist failed, window locked full");
        }
        fill_persist_failure(channel, now_sec, time_synced, out);
        out->pump_allowed = false;
        unlock_state();
        return ESP_ERR_INVALID_STATE;
    }

    unlock_state();
    return ESP_OK;
}

esp_err_t dose_limit_node_rollback(const char *channel, double requested_ml, int64_t now_sec)
{
    if (!lock_state()) {
        return ESP_ERR_INVALID_STATE;
    }
    dose_limit_rollback(&s_state, channel, requested_ml, now_sec);
    if (!persist_locked()) {
        s_state.ledger_untrusted = true;
        ESP_LOGE(TAG, "Rollback persist failed, further doses refused");
        unlock_state();
        return ESP_FAIL;
    }
    unlock_state();
    return ESP_OK;
}

cJSON *dose_limit_result_details(const dose_limit_result_t *result)
{
    cJSON *details;

    if (result == NULL) {
        return NULL;
    }
    details = cJSON_CreateObject();
    if (details == NULL) {
        return NULL;
    }
    cJSON_AddNumberToObject(details, "requested_ml", dose_limit_milli_to_ml(result->requested_milli));
    cJSON_AddNumberToObject(details, "limit_ml", dose_limit_milli_to_ml(result->limit_milli));
    cJSON_AddNumberToObject(details, "used_ml", dose_limit_milli_to_ml(result->used_milli));
    cJSON_AddNumberToObject(details, "remaining_ml", dose_limit_milli_to_ml(result->remaining_milli));
    cJSON_AddNumberToObject(details, "window_hours", DOSE_LIMIT_WINDOW_HOURS);
    return details;
}

esp_err_t dose_limit_node_write_refusal(
    const char *cmd_id,
    const dose_limit_result_t *limit,
    cJSON **response
)
{
    cJSON *extra;

    if (response == NULL || limit == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    extra = dose_limit_result_details(limit);
    *response = node_command_handler_create_response(
        cmd_id,
        "ERROR",
        dose_limit_error_code(limit->code),
        dose_limit_error_message(limit->code),
        extra
    );
    if (extra != NULL) {
        cJSON_Delete(extra);
    }
    return ESP_ERR_INVALID_STATE;
}
