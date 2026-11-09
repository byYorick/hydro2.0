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

void vent_drive_override(vent_drive_t *drive, int target_pct)
{
    int target;
    int delta;

    if (drive == NULL) {
        return;
    }
    target = clamp_pct(target_pct);
    drive->fault = false;
    if (drive->known && drive->position_pct == target && !drive->moving) {
        drive->target_pct = target;
        drive->motor = VENT_STOP;
        return;
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
    vent_arm(drive, target, target == 0 ? VENT_CLOSE : (drive->known && target < drive->position_pct ? VENT_CLOSE : VENT_OPEN), (uint32_t)delta);
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

exhaust_level_t exhaust_hysteresis_step(exhaust_hyst_t *state, bool sensor_valid, float temp_c)
{
    if (state == NULL) {
        return EXHAUST_ON;
    }
    if (!(state->on_c > state->off_c) || !sensor_valid || !isfinite(temp_c)) {
        state->fan_on = true;
        return EXHAUST_ON;
    }
    if (temp_c >= state->on_c) {
        state->fan_on = true;
    } else if (temp_c <= state->off_c) {
        state->fan_on = false;
    }
    return state->fan_on ? EXHAUST_ON : EXHAUST_OFF;
}

void climate_failsafe_decide(
    const climate_fs_input_t *in,
    bool exhaust_request_on,
    climate_fs_output_t *out)
{
    if (out == NULL) {
        return;
    }
    memset(out, 0, sizeof(*out));
    out->reason = CLIMATE_FS_NORMAL;
    out->exhaust_on = exhaust_request_on;
    if (in == NULL) {
        out->deenergize_all = true;
        out->override_remote = true;
        out->exhaust_on = false;
        out->reason = CLIMATE_FS_DRIVER;
        return;
    }
    if (in->estop) {
        out->deenergize_all = true;
        out->override_remote = true;
        out->move_vents = false;
        out->exhaust_on = false;
        out->reason = CLIMATE_FS_ESTOP;
        return;
    }
    if (!in->driver_ok) {
        out->deenergize_all = true;
        out->override_remote = true;
        out->move_vents = false;
        out->exhaust_on = false;
        out->reason = CLIMATE_FS_DRIVER;
        return;
    }
    if (!in->sensor_valid) {
        out->reason = CLIMATE_FS_SENSOR;
        out->override_remote = true;
        if (in->safe_mode == CLIMATE_SAFE_ALL_OFF) {
            out->deenergize_all = true;
            out->exhaust_on = false;
            out->move_vents = false;
            return;
        }
        out->move_vents = true;
        out->vent_target_pct = clamp_pct(in->failsafe_open_pct);
        out->exhaust_on = true;
        return;
    }
    if (isfinite(in->temp_c) && in->temp_c >= in->overheat_c) {
        out->reason = CLIMATE_FS_OVERHEAT;
        out->override_remote = true;
        out->move_vents = true;
        out->vent_target_pct = 100;
        out->exhaust_on = true;
        return;
    }
    if (!in->link_up) {
        out->reason = CLIMATE_FS_LINK;
        out->override_remote = true;
        if (in->safe_mode == CLIMATE_SAFE_ALL_OFF) {
            out->deenergize_all = true;
            out->exhaust_on = false;
            out->move_vents = false;
            return;
        }
        out->exhaust_on = exhaust_request_on;
        if (isfinite(in->temp_c) && in->temp_c >= in->ventilate_above_c) {
            out->move_vents = true;
            out->vent_target_pct = clamp_pct(in->failsafe_open_pct);
        } else if (isfinite(in->temp_c) && in->temp_c <= in->cool_close_c) {
            out->move_vents = true;
            out->vent_target_pct = 0;
        } else {
            out->move_vents = false;
        }
        return;
    }
    out->reason = CLIMATE_FS_NORMAL;
    out->override_remote = false;
    out->move_vents = false;
    out->exhaust_on = exhaust_request_on;
}
