/**
 * Исполнение set_position: проверка параметров и ход привода по времени.
 * Без ESP-IDF. Автономного термостата здесь нет.
 */
#ifndef CLIMATE_CONTROL_LOGIC_H
#define CLIMATE_CONTROL_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CLIMATE_CMD_OK = 0,
    CLIMATE_CMD_INVALID = 1,
    CLIMATE_CMD_NO_EFFECT = 2,
    CLIMATE_CMD_BUSY = 3,
    CLIMATE_CMD_ERROR = 4
} climate_cmd_status_t;

typedef enum {
    VENT_STOP = 0,
    VENT_OPEN = 1,
    VENT_CLOSE = 2
} vent_motor_t;

typedef struct {
    bool known;
    int position_pct;
    int target_pct;
    bool moving;
    vent_motor_t motor;
    uint32_t elapsed_ms;
    uint32_t budget_ms;
    uint32_t travel_full_ms;
    uint32_t timeout_margin_ms;
    bool fault;
} vent_drive_t;

/* position_pct обязателен, конечное число 0..100.
   max_step_pct необязателен; если есть — конечное число 0..100.
   Совпадает с history-logger _validate_command_params для set_position. */
climate_cmd_status_t climate_set_position_validate(
    bool has_position,
    double position_pct,
    bool has_max_step,
    double max_step_pct);

int climate_position_apply_step(
    int current_pct,
    int requested_pct,
    bool has_max_step,
    int max_step_pct);

void vent_drive_init(vent_drive_t *drive, uint32_t travel_full_ms, uint32_t timeout_margin_ms);

climate_cmd_status_t vent_drive_command(vent_drive_t *drive, int target_pct, int deadband_pct);

void vent_drive_halt(vent_drive_t *drive);

/* closed_limit / open_limit — концевик сработал.
   target 0 без концевика закрытия к концу бюджета — fault, мотор стоп.
   Промежуточная цель считается по времени хода. */
vent_motor_t vent_drive_step(
    vent_drive_t *drive,
    uint32_t dt_ms,
    bool closed_limit,
    bool open_limit,
    bool driver_fault);

#ifdef __cplusplus
}
#endif

#endif /* CLIMATE_CONTROL_LOGIC_H */
