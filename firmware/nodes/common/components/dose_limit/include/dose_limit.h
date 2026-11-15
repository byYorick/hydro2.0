/**
 * @file dose_limit.h
 * @brief Лимиты одной дозы и скользящих 24 ч для дозирующих насосов.
 *
 * Каналы: pump_acid, pump_base, pump_a..pump_d (алиасы ph_doser_* сводятся
 * к каноническим именам). Логика без ESP-IDF, чтобы её гонял host-тест.
 *
 * Окно — часовые корзины. Корзина учитывается целиком, пока её час ещё
 * пересекает последние 24 ч, поэтому учёт может быть до часа длиннее
 * строгого окна. Это переучёт, не недоучёт. Скачок часов назад корзины
 * не выбрасывает. Ребут не обнуляет и не удваивает сумму: её несёт blob.
 *
 * Нет валидного времени (time_synced=false или now<=0) — доза не принимается,
 * blob не меняется. Битый blob помечает журнал недоверенным: окно считается
 * исчерпанным, пока NVS не сотрут целиком.
 *
 * Превышение лимита не урезает дозу. pump_allowed=false, миллилитры не пишутся.
 * Равенство лимиту разрешено.
 */

#ifndef DOSE_LIMIT_H
#define DOSE_LIMIT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DOSE_LIMIT_MILLI_PER_ML 1000
#define DOSE_LIMIT_WINDOW_SEC (24 * 60 * 60)
#define DOSE_LIMIT_HOUR_SEC 3600
#define DOSE_LIMIT_WINDOW_HOURS 24

/** Физический потолок одной дозы, мл. Выше — отказ всего NodeConfig. */
#define DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_ML 500
/** Физический потолок скользящих суток, мл. */
#define DOSE_LIMIT_PHYSICAL_MAX_DAILY_ML 2000

#define DOSE_LIMIT_PH_DEFAULT_PER_DOSE_ML 35
#define DOSE_LIMIT_PH_DEFAULT_DAILY_ML 200
#define DOSE_LIMIT_EC_DEFAULT_PER_DOSE_ML 80
#define DOSE_LIMIT_EC_DEFAULT_DAILY_ML 500

#define DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_MILLI \
    (DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_ML * DOSE_LIMIT_MILLI_PER_ML)
#define DOSE_LIMIT_PHYSICAL_MAX_DAILY_MILLI \
    (DOSE_LIMIT_PHYSICAL_MAX_DAILY_ML * DOSE_LIMIT_MILLI_PER_ML)
#define DOSE_LIMIT_PH_DEFAULT_PER_DOSE_MILLI \
    (DOSE_LIMIT_PH_DEFAULT_PER_DOSE_ML * DOSE_LIMIT_MILLI_PER_ML)
#define DOSE_LIMIT_PH_DEFAULT_DAILY_MILLI \
    (DOSE_LIMIT_PH_DEFAULT_DAILY_ML * DOSE_LIMIT_MILLI_PER_ML)
#define DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI \
    (DOSE_LIMIT_EC_DEFAULT_PER_DOSE_ML * DOSE_LIMIT_MILLI_PER_ML)
#define DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI \
    (DOSE_LIMIT_EC_DEFAULT_DAILY_ML * DOSE_LIMIT_MILLI_PER_ML)

#define DOSE_LIMIT_CHANNEL_NAME_MAX 16
#define DOSE_LIMIT_MAX_CHANNELS 6
#define DOSE_LIMIT_MAX_BUCKETS 26
#define DOSE_LIMIT_BLOB_MAX 2048

#define DOSE_LIMIT_ERR_PER_DOSE "dose_limit_per_dose"
#define DOSE_LIMIT_ERR_DAILY "dose_limit_daily"
#define DOSE_LIMIT_ERR_TIME "dose_limit_time_unsynced"
#define DOSE_LIMIT_ERR_CHANNEL "dose_limit_unknown_channel"
#define DOSE_LIMIT_ERR_PERSIST "dose_limit_persist_failed"
#define DOSE_LIMIT_ERR_UNAVAILABLE "dose_limit_unavailable"

typedef enum {
    DOSE_LIMIT_CHANNEL_NONE = 0,
    DOSE_LIMIT_CHANNEL_PH,
    DOSE_LIMIT_CHANNEL_EC,
} dose_limit_channel_kind_t;

typedef enum {
    DOSE_LIMIT_ALLOW = 0,
    DOSE_LIMIT_PER_DOSE,
    DOSE_LIMIT_DAILY,
    DOSE_LIMIT_TIME_UNSYNCED,
    DOSE_LIMIT_UNKNOWN_CHANNEL,
    DOSE_LIMIT_PERSIST_FAILED,
    DOSE_LIMIT_UNAVAILABLE,
} dose_limit_code_t;

typedef enum {
    DOSE_LIMIT_FIELD_ABSENT = 0,
    DOSE_LIMIT_FIELD_NUMBER,
    DOSE_LIMIT_FIELD_INVALID,
} dose_limit_field_status_t;

typedef struct {
    dose_limit_field_status_t status;
    double value;
} dose_limit_field_t;

typedef enum {
    DOSE_LIMIT_CONFIG_OK = 0,
    DOSE_LIMIT_CONFIG_REJECT,
} dose_limit_config_status_t;

typedef struct {
    const char *name;
    dose_limit_field_t per_dose;
    dose_limit_field_t daily;
} dose_limit_channel_input_t;

typedef struct {
    int64_t hour_start_sec;
    int32_t milli_ml;
} dose_limit_bucket_t;

typedef struct {
    char name[DOSE_LIMIT_CHANNEL_NAME_MAX];
    dose_limit_channel_kind_t kind;
    int32_t per_dose_milli;
    int32_t daily_milli;
    uint8_t bucket_count;
    dose_limit_bucket_t buckets[DOSE_LIMIT_MAX_BUCKETS];
} dose_limit_channel_t;

typedef struct {
    bool ledger_untrusted;
    uint8_t channel_count;
    dose_limit_channel_t channels[DOSE_LIMIT_MAX_CHANNELS];
} dose_limit_state_t;

typedef struct {
    dose_limit_code_t code;
    bool pump_allowed;
    int32_t requested_milli;
    int32_t limit_milli;
    int32_t used_milli;
    int32_t remaining_milli;
} dose_limit_result_t;

dose_limit_channel_kind_t dose_limit_channel_kind(const char *name);
const char *dose_limit_canonical_channel(const char *name);

dose_limit_field_t dose_limit_field_absent(void);
dose_limit_field_t dose_limit_field_from_number(bool present, bool is_number, double value);

/**
 * @brief Проверка пары лимитов. Отказ не клампит: out_* пишутся только при OK.
 *
 * Нет поля — дефолт канала. 0, отрицательное, нечисло и значение выше
 * физического максимума — REJECT. Сутки меньше разовой дозы — тоже REJECT.
 */
dose_limit_config_status_t dose_limit_resolve_limits(
    dose_limit_channel_kind_t kind,
    dose_limit_field_t per_dose,
    dose_limit_field_t daily,
    int32_t *out_per_milli,
    int32_t *out_daily_milli,
    const char **out_reason
);

/**
 * @brief Первая плохая дозирующая строка отклоняет весь набор.
 * Каналы не из списка дозаторов пропускаются.
 */
dose_limit_config_status_t dose_limit_validate_channels(
    const dose_limit_channel_input_t *channels,
    size_t count,
    const char **out_channel,
    const char **out_reason
);

void dose_limit_init(dose_limit_state_t *state);

/** Обновляет лимиты канала. Уже записанные корзины не стирает. */
bool dose_limit_bind(dose_limit_state_t *state, const char *canonical_name, int32_t per_dose_milli, int32_t daily_milli);

bool dose_limit_channel_limits(
    const dose_limit_state_t *state,
    const char *channel,
    int32_t *per_dose_milli,
    int32_t *daily_milli
);

int32_t dose_limit_active_used_milli(
    const dose_limit_state_t *state,
    const char *channel,
    int64_t now_sec,
    bool time_synced
);

/**
 * @brief Принять дозу или отказать, не включая насос.
 * ALLOW записывает полные requested мл в окно. Отказ окно не меняет.
 */
dose_limit_code_t dose_limit_authorize(
    dose_limit_state_t *state,
    const char *channel,
    double requested_ml,
    int64_t now_sec,
    bool time_synced,
    dose_limit_result_t *out
);

/** Снять ранее принятую дозу (enqueue не удался). Повторный вызов уменьшит корзину ещё раз. */
void dose_limit_rollback(
    dose_limit_state_t *state,
    const char *channel,
    double requested_ml,
    int64_t now_sec
);

bool dose_limit_export(const dose_limit_state_t *state, uint8_t *buf, size_t cap, size_t *out_len);

/**
 * @brief Восстановить корзины. Лимиты канала не трогает.
 * Битый blob: ledger_untrusted, корзины пустые, return false.
 */
bool dose_limit_import(dose_limit_state_t *state, const uint8_t *buf, size_t len);

const char *dose_limit_error_code(dose_limit_code_t code);
const char *dose_limit_error_message(dose_limit_code_t code);
double dose_limit_milli_to_ml(int32_t milli);

#ifdef __cplusplus
}
#endif

#endif /* DOSE_LIMIT_H */
