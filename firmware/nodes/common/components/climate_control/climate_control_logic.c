#include "climate_control_logic.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static int clamp_pct(int value)
{
    if (value < 0) {
        return 0;
    }
    if (value > 100) {
        return 100;
    }
    return value;
}

static uint32_t travel_budget(const vent_drive_t *drive, uint32_t delta_pct)
{
    uint32_t span = drive->travel_full_ms;
    uint32_t margin = drive->timeout_margin_ms;
    uint32_t body;

    if (span == 0) {
        span = 60000u;
    }
    if (delta_pct > 100u) {
        delta_pct = 100u;
    }
    body = (span * delta_pct) / 100u;
    if (body + margin < body) {
        return UINT32_MAX;
    }
    if (body + margin == 0u) {
        return 1u;
    }
    return body + margin;
}

static void vent_arm(vent_drive_t *drive, int target_pct, vent_motor_t motor, uint32_t delta_pct)
{
    drive->target_pct = clamp_pct(target_pct);
    drive->motor = motor;
    drive->moving = motor != VENT_STOP;
    drive->elapsed_ms = 0;
    drive->fault = false;
    drive->budget_ms = travel_budget(drive, delta_pct == 0 ? 100u : delta_pct);
    if (motor == VENT_STOP) {
        drive->moving = false;
        drive->budget_ms = 0;
    }
}

climate_cmd_status_t climate_set_position_validate(
    bool has_position,
    double position_pct,
    bool has_max_step,
    double max_step_pct)
{
    if (!has_position || !isfinite(position_pct) || position_pct < 0.0 || position_pct > 100.0) {
        return CLIMATE_CMD_INVALID;
    }
    if (has_max_step && (!isfinite(max_step_pct) || max_step_pct < 0.0 || max_step_pct > 100.0)) {
        return CLIMATE_CMD_INVALID;
    }
    return CLIMATE_CMD_OK;
}

int climate_position_apply_step(
    int current_pct,
    int requested_pct,
    bool has_max_step,
    int max_step_pct)
{
    int current = clamp_pct(current_pct);
    int requested = clamp_pct(requested_pct);
    int delta = requested - current;
    int step;

    if (!has_max_step) {
        return requested;
    }
    if (max_step_pct < 0) {
        max_step_pct = 0;
    }
    if (max_step_pct > 100) {
        max_step_pct = 100;
    }
    if (delta > max_step_pct) {
        step = max_step_pct;
    } else if (delta < -max_step_pct) {
        step = -max_step_pct;
    } else {
        step = delta;
    }
    return clamp_pct(current + step);
}

void vent_drive_init(vent_drive_t *drive, uint32_t travel_full_ms, uint32_t timeout_margin_ms)
{
    if (drive == NULL) {
        return;
    }
    memset(drive, 0, sizeof(*drive));
    drive->travel_full_ms = travel_full_ms == 0u ? 60000u : travel_full_ms;
    drive->timeout_margin_ms = timeout_margin_ms;
    drive->motor = VENT_STOP;
}

climate_cmd_status_t vent_drive_command(vent_drive_t *drive, int target_pct, int deadband_pct)
{
    int target;
    int delta;

    if (drive == NULL) {
        return CLIMATE_CMD_ERROR;
    }
    if (drive->fault) {
        return CLIMATE_CMD_ERROR;
    }
    if (drive->moving) {
        return CLIMATE_CMD_BUSY;
    }
    target = clamp_pct(target_pct);
    if (deadband_pct < 0) {
        deadband_pct = 0;
    }
    if (drive->known && abs(drive->position_pct - target) <= deadband_pct) {
        return CLIMATE_CMD_NO_EFFECT;
    }
    if (!drive->known) {
        delta = 100;
    } else if (target >= drive->position_pct) {
        delta = target - drive->position_pct;
    } else {
        delta = drive->position_pct - target;
    }
    if (delta == 0) {
        delta = 1;
    }
    vent_arm(drive, target, target >= (drive->known ? drive->position_pct : 1) ? VENT_OPEN : VENT_CLOSE, (uint32_t)delta);
    if (target == 0) {
        drive->motor = VENT_CLOSE;
        drive->moving = true;
    }
    return CLIMATE_CMD_OK;
}

void vent_drive_halt(vent_drive_t *drive)
{
    if (drive == NULL) {
        return;
    }
    drive->moving = false;
    drive->motor = VENT_STOP;
    drive->elapsed_ms = 0;
}

vent_motor_t vent_drive_step(
    vent_drive_t *drive,
    uint32_t dt_ms,
    bool closed_limit,
    bool open_limit,
    bool driver_fault)
{
    uint32_t next;

    if (drive == NULL) {
        return VENT_STOP;
    }
    if (driver_fault) {
        drive->fault = true;
        drive->known = false;
        drive->moving = false;
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }
    if (!drive->moving) {
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }
    if (drive->motor == VENT_CLOSE && closed_limit) {
        drive->position_pct = 0;
        drive->known = true;
        drive->fault = false;
        drive->moving = false;
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }
    if (drive->motor == VENT_OPEN && open_limit) {
        drive->position_pct = 100;
        drive->known = true;
        drive->fault = false;
        drive->moving = false;
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }
    if ((drive->motor == VENT_OPEN && closed_limit) || (drive->motor == VENT_CLOSE && open_limit)) {
        drive->fault = true;
        drive->known = false;
        drive->moving = false;
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }

    next = drive->elapsed_ms + dt_ms;
    if (next < drive->elapsed_ms) {
        next = UINT32_MAX;
    }
    drive->elapsed_ms = next;
    if (drive->elapsed_ms < drive->budget_ms) {
        return drive->motor;
    }

    if (drive->target_pct == 0) {
        drive->fault = true;
        drive->known = false;
        drive->moving = false;
        drive->motor = VENT_STOP;
        return VENT_STOP;
    }

    drive->position_pct = drive->target_pct;
    drive->known = true;
    drive->fault = false;
    drive->moving = false;
    drive->motor = VENT_STOP;
    return VENT_STOP;
}
