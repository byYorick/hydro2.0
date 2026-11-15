#include "dose_limit.h"

#include <math.h>
#include <string.h>

#define DOSE_LIMIT_BLOB_MAGIC 0x314D4C44u
#define DOSE_LIMIT_BLOB_VERSION 1u

static int32_t default_per_milli(dose_limit_channel_kind_t kind)
{
    if (kind == DOSE_LIMIT_CHANNEL_EC) {
        return DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI;
    }
    return DOSE_LIMIT_PH_DEFAULT_PER_DOSE_MILLI;
}

static int32_t default_daily_milli(dose_limit_channel_kind_t kind)
{
    if (kind == DOSE_LIMIT_CHANNEL_EC) {
        return DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI;
    }
    return DOSE_LIMIT_PH_DEFAULT_DAILY_MILLI;
}

static bool name_eq(const char *left, const char *right)
{
    return left != NULL && right != NULL && strcmp(left, right) == 0;
}

dose_limit_channel_kind_t dose_limit_channel_kind(const char *name)
{
    if (name_eq(name, "pump_acid") || name_eq(name, "pump_base") ||
        name_eq(name, "ph_doser_down") || name_eq(name, "ph_doser_up")) {
        return DOSE_LIMIT_CHANNEL_PH;
    }
    if (name_eq(name, "pump_a") || name_eq(name, "pump_b") ||
        name_eq(name, "pump_c") || name_eq(name, "pump_d")) {
        return DOSE_LIMIT_CHANNEL_EC;
    }
    return DOSE_LIMIT_CHANNEL_NONE;
}

const char *dose_limit_canonical_channel(const char *name)
{
    if (name_eq(name, "ph_doser_down")) {
        return "pump_acid";
    }
    if (name_eq(name, "ph_doser_up")) {
        return "pump_base";
    }
    if (dose_limit_channel_kind(name) == DOSE_LIMIT_CHANNEL_NONE) {
        return NULL;
    }
    return name;
}

dose_limit_field_t dose_limit_field_absent(void)
{
    dose_limit_field_t field;
    field.status = DOSE_LIMIT_FIELD_ABSENT;
    field.value = 0.0;
    return field;
}

dose_limit_field_t dose_limit_field_from_number(bool present, bool is_number, double value)
{
    dose_limit_field_t field = dose_limit_field_absent();
    if (!present) {
        return field;
    }
    if (!is_number || !isfinite(value)) {
        field.status = DOSE_LIMIT_FIELD_INVALID;
        return field;
    }
    field.status = DOSE_LIMIT_FIELD_NUMBER;
    field.value = value;
    return field;
}

static bool ml_to_milli(double ml, int32_t *out)
{
    double scaled;
    long long rounded;

    if (out == NULL || !isfinite(ml)) {
        return false;
    }
    if (ml > 1000000.0 || ml < -1000000.0) {
        return false;
    }
    scaled = ml * (double)DOSE_LIMIT_MILLI_PER_ML;
    if (!isfinite(scaled)) {
        return false;
    }
    rounded = llround(scaled);
    if (rounded > 2147483647LL || rounded < -2147483647LL) {
        return false;
    }
    *out = (int32_t)rounded;
    return true;
}

static dose_limit_config_status_t reject_limits(const char **out_reason, const char *reason)
{
    if (out_reason != NULL) {
        *out_reason = reason;
    }
    return DOSE_LIMIT_CONFIG_REJECT;
}

static dose_limit_config_status_t check_explicit_milli(
    int32_t milli,
    int32_t physical_max,
    const char *range_reason,
    const char **out_reason
)
{
    if (milli <= 0 || milli > physical_max) {
        return reject_limits(out_reason, range_reason);
    }
    return DOSE_LIMIT_CONFIG_OK;
}

dose_limit_config_status_t dose_limit_resolve_limits(
    dose_limit_channel_kind_t kind,
    dose_limit_field_t per_dose,
    dose_limit_field_t daily,
    int32_t *out_per_milli,
    int32_t *out_daily_milli,
    const char **out_reason
)
{
    int32_t per_milli;
    int32_t daily_milli;

    if (kind != DOSE_LIMIT_CHANNEL_PH && kind != DOSE_LIMIT_CHANNEL_EC) {
        return reject_limits(out_reason, "not a dosing channel");
    }
    if (per_dose.status == DOSE_LIMIT_FIELD_INVALID) {
        return reject_limits(out_reason, "max_dose_ml is not a number");
    }
    if (daily.status == DOSE_LIMIT_FIELD_INVALID) {
        return reject_limits(out_reason, "max_daily_ml is not a number");
    }

    if (per_dose.status == DOSE_LIMIT_FIELD_ABSENT) {
        per_milli = default_per_milli(kind);
    } else if (!ml_to_milli(per_dose.value, &per_milli)) {
        return reject_limits(out_reason, "max_dose_ml is not a number");
    }
    if (check_explicit_milli(
            per_milli,
            DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_MILLI,
            "max_dose_ml must be > 0 and <= 500",
            out_reason) != DOSE_LIMIT_CONFIG_OK) {
        return DOSE_LIMIT_CONFIG_REJECT;
    }

    if (daily.status == DOSE_LIMIT_FIELD_ABSENT) {
        daily_milli = default_daily_milli(kind);
    } else if (!ml_to_milli(daily.value, &daily_milli)) {
        return reject_limits(out_reason, "max_daily_ml is not a number");
    }
    if (check_explicit_milli(
            daily_milli,
            DOSE_LIMIT_PHYSICAL_MAX_DAILY_MILLI,
            "max_daily_ml must be > 0 and <= 2000",
            out_reason) != DOSE_LIMIT_CONFIG_OK) {
        return DOSE_LIMIT_CONFIG_REJECT;
    }
    if (daily_milli < per_milli) {
        return reject_limits(out_reason, "max_daily_ml is below max_dose_ml");
    }

    if (out_per_milli != NULL) {
        *out_per_milli = per_milli;
    }
    if (out_daily_milli != NULL) {
        *out_daily_milli = daily_milli;
    }
    if (out_reason != NULL) {
        *out_reason = NULL;
    }
    return DOSE_LIMIT_CONFIG_OK;
}

dose_limit_config_status_t dose_limit_validate_channels(
    const dose_limit_channel_input_t *channels,
    size_t count,
    const char **out_channel,
    const char **out_reason
)
{
    size_t i;

    if (out_channel != NULL) {
        *out_channel = NULL;
    }
    if (channels == NULL && count > 0) {
        return reject_limits(out_reason, "channels missing");
    }
    for (i = 0; i < count; i++) {
        dose_limit_channel_kind_t kind = dose_limit_channel_kind(channels[i].name);
        int32_t per_milli = 0;
        int32_t daily_milli = 0;
        const char *reason = NULL;

        if (kind == DOSE_LIMIT_CHANNEL_NONE) {
            continue;
        }
        if (dose_limit_resolve_limits(
                kind,
                channels[i].per_dose,
                channels[i].daily,
                &per_milli,
                &daily_milli,
                &reason) != DOSE_LIMIT_CONFIG_OK) {
            if (out_channel != NULL) {
                *out_channel = channels[i].name;
            }
            return reject_limits(out_reason, reason != NULL ? reason : "rejected");
        }
    }
    if (out_reason != NULL) {
        *out_reason = NULL;
    }
    return DOSE_LIMIT_CONFIG_OK;
}

void dose_limit_init(dose_limit_state_t *state)
{
    if (state == NULL) {
        return;
    }
    memset(state, 0, sizeof(*state));
}

static dose_limit_channel_t *find_channel(dose_limit_state_t *state, const char *canonical)
{
    uint8_t i;

    if (state == NULL || canonical == NULL) {
        return NULL;
    }
    for (i = 0; i < state->channel_count; i++) {
        if (strcmp(state->channels[i].name, canonical) == 0) {
            return &state->channels[i];
        }
    }
    return NULL;
}

static const dose_limit_channel_t *find_channel_const(const dose_limit_state_t *state, const char *canonical)
{
    uint8_t i;

    if (state == NULL || canonical == NULL) {
        return NULL;
    }
    for (i = 0; i < state->channel_count; i++) {
        if (strcmp(state->channels[i].name, canonical) == 0) {
            return &state->channels[i];
        }
    }
    return NULL;
}

bool dose_limit_bind(
    dose_limit_state_t *state,
    const char *canonical_name,
    int32_t per_dose_milli,
    int32_t daily_milli
)
{
    dose_limit_channel_t *channel;
    dose_limit_channel_kind_t kind;

    if (state == NULL || canonical_name == NULL) {
        return false;
    }
    kind = dose_limit_channel_kind(canonical_name);
    if (kind == DOSE_LIMIT_CHANNEL_NONE || strlen(canonical_name) >= DOSE_LIMIT_CHANNEL_NAME_MAX) {
        return false;
    }
    if (per_dose_milli < 0 || daily_milli < 0) {
        return false;
    }
    channel = find_channel(state, canonical_name);
    if (channel == NULL) {
        if (state->channel_count >= DOSE_LIMIT_MAX_CHANNELS) {
            return false;
        }
        channel = &state->channels[state->channel_count];
        memset(channel, 0, sizeof(*channel));
        memcpy(channel->name, canonical_name, strlen(canonical_name) + 1);
        state->channel_count++;
    }
    channel->kind = kind;
    channel->per_dose_milli = per_dose_milli;
    channel->daily_milli = daily_milli;
    return true;
}

bool dose_limit_channel_limits(
    const dose_limit_state_t *state,
    const char *channel_name,
    int32_t *per_dose_milli,
    int32_t *daily_milli
)
{
    const char *canonical = dose_limit_canonical_channel(channel_name);
    const dose_limit_channel_t *channel = find_channel_const(state, canonical);

    if (channel == NULL) {
        return false;
    }
    if (per_dose_milli != NULL) {
        *per_dose_milli = channel->per_dose_milli;
    }
    if (daily_milli != NULL) {
        *daily_milli = channel->daily_milli;
    }
    return true;
}

static bool bucket_overlaps_window(int64_t hour_start, int64_t now_sec)
{
    int64_t window_start = now_sec - (int64_t)DOSE_LIMIT_WINDOW_SEC;
    int64_t hour_end = hour_start + (int64_t)DOSE_LIMIT_HOUR_SEC;
    return hour_end > window_start;
}

static void compact_channel(dose_limit_channel_t *channel, int64_t now_sec)
{
    uint8_t read;
    uint8_t write = 0;

    for (read = 0; read < channel->bucket_count; read++) {
        if (bucket_overlaps_window(channel->buckets[read].hour_start_sec, now_sec)) {
            if (write != read) {
                channel->buckets[write] = channel->buckets[read];
            }
            write++;
        }
    }
    channel->bucket_count = write;
}

static int32_t sum_buckets(const dose_limit_channel_t *channel, int64_t now_sec, bool expire)
{
    int64_t sum = 0;
    uint8_t i;

    for (i = 0; i < channel->bucket_count; i++) {
        if (!expire || bucket_overlaps_window(channel->buckets[i].hour_start_sec, now_sec)) {
            sum += channel->buckets[i].milli_ml;
        }
    }
    if (sum > 2147483647LL) {
        return 2147483647;
    }
    if (sum < 0) {
        return 0;
    }
    return (int32_t)sum;
}

int32_t dose_limit_active_used_milli(
    const dose_limit_state_t *state,
    const char *channel_name,
    int64_t now_sec,
    bool time_synced
)
{
    const char *canonical = dose_limit_canonical_channel(channel_name);
    const dose_limit_channel_t *channel = find_channel_const(state, canonical);

    if (channel == NULL) {
        return 0;
    }
    if (state->ledger_untrusted) {
        return channel->daily_milli;
    }
    if (!time_synced || now_sec <= 0) {
        return sum_buckets(channel, now_sec, false);
    }
    return sum_buckets(channel, now_sec, true);
}

static void fill_result(
    dose_limit_result_t *out,
    dose_limit_code_t code,
    bool pump_allowed,
    int32_t requested,
    int32_t limit,
    int32_t used,
    bool remaining_zero
)
{
    int32_t remaining = 0;

    if (!remaining_zero && used < limit) {
        remaining = limit - used;
    }
    if (out == NULL) {
        return;
    }
    out->code = code;
    out->pump_allowed = pump_allowed;
    out->requested_milli = requested;
    out->limit_milli = limit;
    out->used_milli = used;
    out->remaining_milli = remaining;
}

static bool add_milli(dose_limit_channel_t *channel, int64_t now_sec, int32_t milli)
{
    int64_t hour;
    uint8_t i;
    dose_limit_bucket_t *bucket;

    if (now_sec <= 0 || milli <= 0) {
        return false;
    }
    compact_channel(channel, now_sec);
    hour = now_sec - (now_sec % (int64_t)DOSE_LIMIT_HOUR_SEC);
    for (i = 0; i < channel->bucket_count; i++) {
        bucket = &channel->buckets[i];
        if (bucket->hour_start_sec == hour) {
            if ((int64_t)bucket->milli_ml + (int64_t)milli > 2147483647LL) {
                return false;
            }
            bucket->milli_ml += milli;
            return true;
        }
    }
    if (channel->bucket_count >= DOSE_LIMIT_MAX_BUCKETS) {
        return false;
    }
    bucket = &channel->buckets[channel->bucket_count];
    bucket->hour_start_sec = hour;
    bucket->milli_ml = milli;
    channel->bucket_count++;
    return true;
}

dose_limit_code_t dose_limit_authorize(
    dose_limit_state_t *state,
    const char *channel_name,
    double requested_ml,
    int64_t now_sec,
    bool time_synced,
    dose_limit_result_t *out
)
{
    const char *canonical;
    dose_limit_channel_t *channel;
    int32_t requested = 0;
    int32_t used;
    bool time_ok;

    canonical = dose_limit_canonical_channel(channel_name);
    channel = find_channel(state, canonical);
    if (state == NULL || channel == NULL) {
        fill_result(out, DOSE_LIMIT_UNKNOWN_CHANNEL, false, 0, 0, 0, true);
        return DOSE_LIMIT_UNKNOWN_CHANNEL;
    }

    if (!ml_to_milli(requested_ml, &requested) || requested <= 0) {
        fill_result(out, DOSE_LIMIT_PER_DOSE, false, 0, channel->per_dose_milli, 0, false);
        return DOSE_LIMIT_PER_DOSE;
    }

    if (state->ledger_untrusted) {
        fill_result(out, DOSE_LIMIT_DAILY, false, requested, channel->daily_milli, channel->daily_milli, true);
        return DOSE_LIMIT_DAILY;
    }

    time_ok = time_synced && now_sec > 0;
    if (!time_ok) {
        used = sum_buckets(channel, now_sec, false);
        fill_result(out, DOSE_LIMIT_TIME_UNSYNCED, false, requested, channel->daily_milli, used, true);
        return DOSE_LIMIT_TIME_UNSYNCED;
    }

    if (requested > channel->per_dose_milli) {
        fill_result(out, DOSE_LIMIT_PER_DOSE, false, requested, channel->per_dose_milli, 0, false);
        return DOSE_LIMIT_PER_DOSE;
    }

    compact_channel(channel, now_sec);
    used = sum_buckets(channel, now_sec, true);
    if ((int64_t)used + (int64_t)requested > (int64_t)channel->daily_milli) {
        fill_result(out, DOSE_LIMIT_DAILY, false, requested, channel->daily_milli, used, false);
        return DOSE_LIMIT_DAILY;
    }

    if (!add_milli(channel, now_sec, requested)) {
        fill_result(out, DOSE_LIMIT_DAILY, false, requested, channel->daily_milli, channel->daily_milli, true);
        return DOSE_LIMIT_DAILY;
    }

    used = sum_buckets(channel, now_sec, true);
    fill_result(out, DOSE_LIMIT_ALLOW, true, requested, channel->daily_milli, used, false);
    return DOSE_LIMIT_ALLOW;
}

void dose_limit_rollback(
    dose_limit_state_t *state,
    const char *channel_name,
    double requested_ml,
    int64_t now_sec
)
{
    dose_limit_channel_t *channel;
    int32_t requested = 0;
    int64_t hour;
    uint8_t i;

    channel = find_channel(state, dose_limit_canonical_channel(channel_name));
    if (channel == NULL || now_sec <= 0 || !ml_to_milli(requested_ml, &requested) || requested <= 0) {
        return;
    }
    hour = now_sec - (now_sec % (int64_t)DOSE_LIMIT_HOUR_SEC);
    for (i = 0; i < channel->bucket_count; i++) {
        if (channel->buckets[i].hour_start_sec != hour) {
            continue;
        }
        if (channel->buckets[i].milli_ml <= requested) {
            uint8_t j;
            for (j = i + 1; j < channel->bucket_count; j++) {
                channel->buckets[j - 1] = channel->buckets[j];
            }
            channel->bucket_count--;
        } else {
            channel->buckets[i].milli_ml -= requested;
        }
        return;
    }
}

static uint32_t crc32_ieee(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    size_t i;
    int bit;

    for (i = 0; i < len; i++) {
        crc ^= data[i];
        for (bit = 0; bit < 8; bit++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static bool write_bytes(uint8_t **cursor, uint8_t *end, const void *src, size_t len)
{
    if (*cursor + len > end) {
        return false;
    }
    memcpy(*cursor, src, len);
    *cursor += len;
    return true;
}

static bool write_u16(uint8_t **cursor, uint8_t *end, uint16_t value)
{
    uint8_t bytes[2];
    bytes[0] = (uint8_t)(value & 0xFFu);
    bytes[1] = (uint8_t)((value >> 8) & 0xFFu);
    return write_bytes(cursor, end, bytes, sizeof(bytes));
}

static bool write_u32(uint8_t **cursor, uint8_t *end, uint32_t value)
{
    uint8_t bytes[4];
    bytes[0] = (uint8_t)(value & 0xFFu);
    bytes[1] = (uint8_t)((value >> 8) & 0xFFu);
    bytes[2] = (uint8_t)((value >> 16) & 0xFFu);
    bytes[3] = (uint8_t)((value >> 24) & 0xFFu);
    return write_bytes(cursor, end, bytes, sizeof(bytes));
}

static bool write_i32(uint8_t **cursor, uint8_t *end, int32_t value)
{
    return write_u32(cursor, end, (uint32_t)value);
}

static bool write_i64(uint8_t **cursor, uint8_t *end, int64_t value)
{
    uint8_t bytes[8];
    uint64_t u = (uint64_t)value;
    int i;
    for (i = 0; i < 8; i++) {
        bytes[i] = (uint8_t)((u >> (8 * i)) & 0xFFu);
    }
    return write_bytes(cursor, end, bytes, sizeof(bytes));
}

static bool read_bytes(const uint8_t **cursor, const uint8_t *end, void *dst, size_t len)
{
    if (*cursor + len > end) {
        return false;
    }
    memcpy(dst, *cursor, len);
    *cursor += len;
    return true;
}

static bool read_u16(const uint8_t **cursor, const uint8_t *end, uint16_t *value)
{
    uint8_t bytes[2];
    if (!read_bytes(cursor, end, bytes, sizeof(bytes))) {
        return false;
    }
    *value = (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
    return true;
}

static bool read_u32(const uint8_t **cursor, const uint8_t *end, uint32_t *value)
{
    uint8_t bytes[4];
    if (!read_bytes(cursor, end, bytes, sizeof(bytes))) {
        return false;
    }
    *value = (uint32_t)bytes[0] |
             ((uint32_t)bytes[1] << 8) |
             ((uint32_t)bytes[2] << 16) |
             ((uint32_t)bytes[3] << 24);
    return true;
}

static bool read_i32(const uint8_t **cursor, const uint8_t *end, int32_t *value)
{
    uint32_t u;
    if (!read_u32(cursor, end, &u)) {
        return false;
    }
    *value = (int32_t)u;
    return true;
}

static bool read_i64(const uint8_t **cursor, const uint8_t *end, int64_t *value)
{
    uint8_t bytes[8];
    uint64_t u = 0;
    int i;
    if (!read_bytes(cursor, end, bytes, sizeof(bytes))) {
        return false;
    }
    for (i = 0; i < 8; i++) {
        u |= ((uint64_t)bytes[i]) << (8 * i);
    }
    *value = (int64_t)u;
    return true;
}

static void mark_untrusted(dose_limit_state_t *state)
{
    uint8_t i;
    state->ledger_untrusted = true;
    for (i = 0; i < state->channel_count; i++) {
        state->channels[i].bucket_count = 0;
    }
}

bool dose_limit_export(const dose_limit_state_t *state, uint8_t *buf, size_t cap, size_t *out_len)
{
    uint8_t *cursor;
    uint8_t *end;
    uint8_t i;
    uint8_t b;
    uint32_t crc;

    if (out_len != NULL) {
        *out_len = 0;
    }
    if (state == NULL || buf == NULL || cap < 16 || state->ledger_untrusted) {
        return false;
    }
    cursor = buf;
    end = buf + cap;
    if (!write_u32(&cursor, end, DOSE_LIMIT_BLOB_MAGIC) ||
        !write_u16(&cursor, end, DOSE_LIMIT_BLOB_VERSION) ||
        !write_u16(&cursor, end, state->channel_count)) {
        return false;
    }
    for (i = 0; i < state->channel_count; i++) {
        const dose_limit_channel_t *channel = &state->channels[i];
        char name[DOSE_LIMIT_CHANNEL_NAME_MAX];

        memset(name, 0, sizeof(name));
        memcpy(name, channel->name, sizeof(name));
        if (!write_bytes(&cursor, end, name, sizeof(name)) ||
            !write_bytes(&cursor, end, &channel->bucket_count, 1)) {
            return false;
        }
        for (b = 0; b < channel->bucket_count; b++) {
            if (!write_i64(&cursor, end, channel->buckets[b].hour_start_sec) ||
                !write_i32(&cursor, end, channel->buckets[b].milli_ml)) {
                return false;
            }
        }
    }
    if (cursor + 4 > end) {
        return false;
    }
    crc = crc32_ieee(buf, (size_t)(cursor - buf));
    if (!write_u32(&cursor, end, crc)) {
        return false;
    }
    if (out_len != NULL) {
        *out_len = (size_t)(cursor - buf);
    }
    return true;
}

bool dose_limit_import(dose_limit_state_t *state, const uint8_t *buf, size_t len)
{
    const uint8_t *cursor;
    const uint8_t *end;
    const uint8_t *crc_at;
    uint32_t magic = 0;
    uint16_t version = 0;
    uint16_t channel_count = 0;
    uint32_t stored_crc = 0;
    uint32_t actual_crc;
    uint16_t i;

    if (state == NULL || buf == NULL || len < 12) {
        if (state != NULL) {
            mark_untrusted(state);
        }
        return false;
    }
    crc_at = buf + len - 4;
    actual_crc = crc32_ieee(buf, len - 4);
    cursor = crc_at;
    end = buf + len;
    if (!read_u32(&cursor, end, &stored_crc) || stored_crc != actual_crc) {
        mark_untrusted(state);
        return false;
    }

    cursor = buf;
    end = crc_at;
    if (!read_u32(&cursor, end, &magic) ||
        !read_u16(&cursor, end, &version) ||
        !read_u16(&cursor, end, &channel_count) ||
        magic != DOSE_LIMIT_BLOB_MAGIC ||
        version != DOSE_LIMIT_BLOB_VERSION ||
        channel_count > DOSE_LIMIT_MAX_CHANNELS) {
        mark_untrusted(state);
        return false;
    }

    for (i = 0; i < state->channel_count; i++) {
        state->channels[i].bucket_count = 0;
    }

    for (i = 0; i < channel_count; i++) {
        char name[DOSE_LIMIT_CHANNEL_NAME_MAX];
        uint8_t bucket_count = 0;
        uint8_t b;
        dose_limit_channel_t *channel;
        dose_limit_bucket_t parsed[DOSE_LIMIT_MAX_BUCKETS];

        memset(name, 0, sizeof(name));
        if (!read_bytes(&cursor, end, name, sizeof(name)) ||
            !read_bytes(&cursor, end, &bucket_count, 1)) {
            mark_untrusted(state);
            return false;
        }
        name[DOSE_LIMIT_CHANNEL_NAME_MAX - 1] = '\0';
        if (bucket_count > DOSE_LIMIT_MAX_BUCKETS) {
            mark_untrusted(state);
            return false;
        }
        for (b = 0; b < bucket_count; b++) {
            if (!read_i64(&cursor, end, &parsed[b].hour_start_sec) ||
                !read_i32(&cursor, end, &parsed[b].milli_ml) ||
                parsed[b].milli_ml < 0) {
                mark_untrusted(state);
                return false;
            }
        }
        channel = find_channel(state, name);
        if (channel == NULL) {
            continue;
        }
        memcpy(channel->buckets, parsed, sizeof(parsed[0]) * bucket_count);
        channel->bucket_count = bucket_count;
    }
    if (cursor != end) {
        mark_untrusted(state);
        return false;
    }
    state->ledger_untrusted = false;
    return true;
}

const char *dose_limit_error_code(dose_limit_code_t code)
{
    switch (code) {
        case DOSE_LIMIT_ALLOW:
            return NULL;
        case DOSE_LIMIT_PER_DOSE:
            return DOSE_LIMIT_ERR_PER_DOSE;
        case DOSE_LIMIT_DAILY:
            return DOSE_LIMIT_ERR_DAILY;
        case DOSE_LIMIT_TIME_UNSYNCED:
            return DOSE_LIMIT_ERR_TIME;
        case DOSE_LIMIT_UNKNOWN_CHANNEL:
            return DOSE_LIMIT_ERR_CHANNEL;
        case DOSE_LIMIT_PERSIST_FAILED:
            return DOSE_LIMIT_ERR_PERSIST;
        case DOSE_LIMIT_UNAVAILABLE:
            return DOSE_LIMIT_ERR_UNAVAILABLE;
        default:
            return DOSE_LIMIT_ERR_DAILY;
    }
}

const char *dose_limit_error_message(dose_limit_code_t code)
{
    switch (code) {
        case DOSE_LIMIT_PER_DOSE:
            return "Dose exceeds per-dose limit";
        case DOSE_LIMIT_DAILY:
            return "Dose exceeds rolling 24h limit";
        case DOSE_LIMIT_TIME_UNSYNCED:
            return "Dose refused until time is synchronized";
        case DOSE_LIMIT_UNKNOWN_CHANNEL:
            return "Dose channel is not limited";
        case DOSE_LIMIT_PERSIST_FAILED:
            return "Dose refused because the ledger could not be saved";
        case DOSE_LIMIT_UNAVAILABLE:
            return "Dose limiter is not ready";
        case DOSE_LIMIT_ALLOW:
        default:
            return "Dose refused";
    }
}

double dose_limit_milli_to_ml(int32_t milli)
{
    return (double)milli / (double)DOSE_LIMIT_MILLI_PER_ML;
}
