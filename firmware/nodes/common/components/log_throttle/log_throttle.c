/**
 * @file log_throttle.c
 * @brief Простая защита от спама логов по ключу и интервалу.
 */

#include "log_throttle.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

#define LOG_THROTTLE_MAX_ENTRIES 32

typedef struct {
    uint64_t key_hash;
    uint32_t key_len;
    uint64_t last_ts_us;
} log_throttle_entry_t;

static log_throttle_entry_t s_entries[LOG_THROTTLE_MAX_ENTRIES];
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;

static uint64_t log_throttle_hash(const char *key, size_t *out_len) {
    const uint64_t fnv_offset = 14695981039346656037ULL;
    const uint64_t fnv_prime = 1099511628211ULL;
    uint64_t hash = fnv_offset;
    size_t len = 0;

    for (const unsigned char *p = (const unsigned char *)key; *p != '\0'; p++) {
        hash ^= (uint64_t)(*p);
        hash *= fnv_prime;
        len++;
    }

    if (out_len != NULL) {
        *out_len = len;
    }
    return hash;
}

bool log_throttle_allow(const char *key, uint32_t interval_ms) {
    if (key == NULL || interval_ms == 0) {
        return true;
    }

    const uint64_t now_us = esp_timer_get_time();
    const uint64_t interval_us = (uint64_t)interval_ms * 1000ULL;
    size_t key_len = 0;
    const uint64_t key_hash = log_throttle_hash(key, &key_len);
    if (key_len == 0) {
        return true;
    }
    bool allow = true;
    int free_index = -1;

    portENTER_CRITICAL(&s_lock);
    for (int i = 0; i < LOG_THROTTLE_MAX_ENTRIES; i++) {
        if (s_entries[i].key_len == key_len && s_entries[i].key_hash == key_hash) {
            if (now_us - s_entries[i].last_ts_us < interval_us) {
                allow = false;
            } else {
                s_entries[i].last_ts_us = now_us;
            }
            portEXIT_CRITICAL(&s_lock);
            return allow;
        }
        if (s_entries[i].key_len == 0 && free_index < 0) {
            free_index = i;
        }
    }

    if (free_index >= 0) {
        s_entries[free_index].key_hash = key_hash;
        s_entries[free_index].key_len = (uint32_t)key_len;
        s_entries[free_index].last_ts_us = now_us;
    }
    portEXIT_CRITICAL(&s_lock);

    return true;
}
