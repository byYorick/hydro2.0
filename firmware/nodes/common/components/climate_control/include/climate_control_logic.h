/**
 * Чистая логика фрамуг и вытяжки climate_node.
 * Без ESP-IDF: тот же файл собирается host-тестом.
 *
 * Безопасное состояние летней теплицы — вентиляция, пока нет E-STOP
 * и драйвер исправен. Неизвестный датчик не закрывает контур.
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

typedef struct {
    float on_c;
    float off_c;
    bool fan_on;
} exhaust_hyst_t;

typedef enum {
    EXHAUST_OFF = 0,
    EXHAUST_ON = 1
} exhaust_level_t;

typedef enum {
    CLIMATE_SAFE_VENTILATE_ABOVE = 0,
    CLIMATE_SAFE_ALL_OFF = 1
} climate_safe_mode_t;

typedef enum {
    CLIMATE_FS_NORMAL = 0,
    CLIMATE_FS_ESTOP = 1,
    CLIMATE_FS_DRIVER = 2,
    CLIMATE_FS_SENSOR = 3,
    CLIMATE_FS_OVERHEAT = 4,
    CLIMATE_FS_LINK = 5
} climate_fs_reason_t;

typedef struct {
    bool estop;
    bool driver_ok;
    bool sensor_valid;
    float temp_c;
    bool link_up;
    climate_safe_mode_t safe_mode;
    float ventilate_above_c;
    float overheat_c;
    int failsafe_open_pct;
    float cool_close_c;
} climate_fs_input_t;

typedef struct {
    bool override_remote;
    bool move_vents;
    bool deenergize_all;
    bool exhaust_on;
    int vent_target_pct;
    climate_fs_reason_t reason;
} climate_fs_output_t;

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

/* Локальный override: можно сменить цель на ходу. Не для MQTT-команды. */
void vent_drive_override(vent_drive_t *drive, int target_pct);

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

/* on_c должен быть строго выше off_c, иначе вытяжка включается (не молчим).
   Нет датчика — ON. Между порогами держим предыдущее состояние. */
exhaust_level_t exhaust_hysteresis_step(exhaust_hyst_t *state, bool sensor_valid, float temp_c);

void climate_failsafe_decide(
    const climate_fs_input_t *in,
    bool exhaust_request_on,
    climate_fs_output_t *out);

#ifdef __cplusplus
}
#endif

#endif /* CLIMATE_CONTROL_LOGIC_H */
