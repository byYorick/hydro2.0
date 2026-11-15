/**
 * @file link_loss_timeout.c
 * @brief Чистая проверка link_loss_timeout_sec (ADR-0003).
 */

#include "link_loss_timeout.h"

link_loss_timeout_field_t link_loss_timeout_field_absent(void)
{
    link_loss_timeout_field_t field = {
        .status = LINK_LOSS_TIMEOUT_ABSENT,
        .value = 0,
    };
    return field;
}

link_loss_timeout_field_t link_loss_timeout_field_from_number(bool present, bool is_number, double value)
{
    link_loss_timeout_field_t field = link_loss_timeout_field_absent();
    long truncated;

    if (!present) {
        return field;
    }

    field.status = LINK_LOSS_TIMEOUT_INVALID;
    if (!is_number || value != value) {
        return field;
    }
    if (value < -1000000.0 || value > 1000000.0) {
        return field;
    }

    truncated = (long)value;
    if ((double)truncated != value) {
        return field;
    }
    if (truncated < LINK_LOSS_TIMEOUT_SEC_MIN || truncated > LINK_LOSS_TIMEOUT_SEC_MAX) {
        return field;
    }

    field.status = LINK_LOSS_TIMEOUT_VALID;
    field.value = (int32_t)truncated;
    return field;
}

link_loss_timeout_resolve_status_t link_loss_timeout_resolve(
    link_loss_timeout_field_t top,
    link_loss_timeout_field_t guards,
    uint32_t *out_sec
)
{
    int32_t chosen;

    if (top.status == LINK_LOSS_TIMEOUT_INVALID || guards.status == LINK_LOSS_TIMEOUT_INVALID) {
        return LINK_LOSS_TIMEOUT_RESOLVE_REJECTED;
    }
    if (top.status == LINK_LOSS_TIMEOUT_VALID && guards.status == LINK_LOSS_TIMEOUT_VALID
        && top.value != guards.value) {
        return LINK_LOSS_TIMEOUT_RESOLVE_REJECTED;
    }

    if (top.status == LINK_LOSS_TIMEOUT_VALID) {
        chosen = top.value;
    } else if (guards.status == LINK_LOSS_TIMEOUT_VALID) {
        chosen = guards.value;
    } else {
        if (out_sec) {
            *out_sec = LINK_LOSS_TIMEOUT_SEC_DEFAULT;
        }
        return LINK_LOSS_TIMEOUT_RESOLVE_DEFAULTED;
    }

    if (out_sec) {
        *out_sec = (uint32_t)chosen;
    }
    return LINK_LOSS_TIMEOUT_RESOLVE_ACCEPTED;
}
