/**
 * @file trema_ec.h
 * @brief Драйвер Trema EC/TDS (Flash-I²C, iarduino) для узлов ESP-IDF / FreeRTOS
 *
 * Регистры и семантика полей совпадают с **iarduino_I2C_TDS 1.3.3**; эталон и ссылки:
 * `reference/README.md`, `reference/iarduino_I2C_TDS-1.3.3/src/iarduino_I2C_TDS.{h,cpp}`.
 *
 * **FreeRTOS:** все публичные вызовы сериализуются одним **статическим** mutex; между попытками I²C
 * используются `vTaskDelay` / `esp_rom_delay_us`. Не вызывать из ISR. Не вызывать `trema_ec_*`, удерживая
 * mutex `i2c_bus` той же шины, что и Trema (`trema_ec_get_i2c_bus()` в `trema_ec.c`).
 *
 * ec_node: Trema EC по умолчанию на **I2C_BUS_1**; при legacy-разводке — **I2C_BUS_0** (`trema_ec_set_i2c_bus`).
 */

#ifndef TREMA_EC_H
#define TREMA_EC_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

#include "i2c_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

/** Заводской 7-bit адрес по умолчанию (см. iarduino wiki / NODE_CHANNELS_REFERENCE). */
#define TREMA_EC_ADDR 0x09

/** Второй типичный адрес линейки Flash-I2C на одной шине. */
#define TREMA_EC_ADDR_ALT 0x0AU

/** Старые сборки / совместимость (0x08). */
#define TREMA_EC_ADDR_LEGACY 0x08U

/** Идентификатор модели модуля (`DEF_MODEL_TDS`). */
#define TREMA_EC_DEF_MODEL_TDS 0x19U
#define TREMA_EC_MODEL_ID TREMA_EC_DEF_MODEL_TDS

/** Макс. EC с REG_TDS_EC (raw/1000), как у iarduino `getEC` (0…65.535 mS/cm). Согласовано с `trema_ec_read`. */
#define TREMA_EC_EC_REGISTER_MAX_MSCM (65.535f)

/** Регистры — как `iarduino_I2C_TDS.h` (имена сохранены для сопоставления с эталоном). */
#define REG_FLAGS_0         0x00U
#define REG_BITS_0          0x01U
#define REG_FLAGS_1         0x02U
#define REG_BITS_1          0x03U
#define REG_MODEL           0x04U
#define REG_VERSION         0x05U
#define REG_ADDRESS         0x06U
#define REG_CHIP_ID         0x07U
#define REG_TDS_FREQUENCY_L 0x08U
#define REG_TDS_FREQUENCY_H 0x09U
#define REG_TDS_KNOWN_TDS   0x0AU
#define REG_TDS_KNOWN_TDS_1 0x0CU
#define REG_TDS_KNOWN_TDS_2 0x0EU
#define REG_TDS_CALIBRATION 0x10U
#define REG_TDS_Ka          0x11U
#define REG_TDS_Kb          0x14U
#define REG_TDS_Kt          0x16U
#define REG_TDS_Kp          0x18U
#define REG_TDS_t           0x19U
#define REG_TDS_T           0x1AU
#define REG_TDS_Ro          0x1BU
#define REG_TDS_Vout        0x1EU
#define REG_TDS_S           0x20U
#define REG_TDS_EC          0x22U
#define REG_TDS_TDS         0x24U

/** Флаги/биты калибровки — как в `iarduino_I2C_TDS.h`. */
#define TDS_FLG_STATUS_2    0x80U
#define TDS_FLG_STATUS_1    0x40U
#define TDS_BIT_CALC_ERR    0x10U
#define TDS_BIT_CALC_2      0x02U
#define TDS_BIT_CALC_1      0x01U
#define TDS_BITS_CALC_INFO  0x0CU
#define TDS_CODE_CALC_SAVE  0x24U

/** Подтяжка SDA/SCL на модуле: флаг в REG_FLAGS_0, бит в REG_BITS_0 (`getPullI2C` / `setPullI2C`). */
#define TREMA_EC_FLG_I2C_UP     0x04U
#define TREMA_EC_BIT_SET_I2C_UP 0x04U

typedef enum {
    TREMA_EC_ERROR_NONE = 0,
    TREMA_EC_ERROR_NOT_INITIALIZED = 1,
    TREMA_EC_ERROR_I2C = 2,
    TREMA_EC_ERROR_INVALID_VALUE = 3
} trema_ec_error_t;

/** Макс. возраст снимка из очереди для OLED без повторного I²C (см. `PH_NODE_PH_TELEMETRY_CACHE_MAX_AGE_MS`). */
#define TREMA_EC_TELEMETRY_CACHE_MAX_AGE_MS 4000U

/**
 * I²C шина Trema EC (по умолчанию I2C_BUS_1).
 * ec_node выставляет шину в init до trema_ec_init(); при сбое bus 1 — fallback на I2C_BUS_0.
 */
void trema_ec_set_i2c_bus(i2c_bus_id_t bus_id);

i2c_bus_id_t trema_ec_get_i2c_bus(void);

/** Задать ожидаемый 7-bit адрес до init (0x08–0x77). */
void trema_ec_set_i2c_address(uint8_t addr_7bit);

/**
 * Снимок EC для телеметрии / очереди (копируется целиком; см. `trema_ph_measurement_t` на ph_node).
 */
typedef struct {
    float ec_mScm;
    uint16_t raw_ec_u16;
    /** ppm из REG_TDS_TDS, снято в том же poll что и EC (без отдельного I²C в publish). */
    uint16_t tds_ppm;
    bool using_stub;
    bool valid;
    TickType_t tick_stamp;
} trema_ec_measurement_t;

/**
 * Привязать очередь глубины 1, sizeof(trema_ec_measurement_t). Заполняется `trema_ec_push_telemetry_snapshot`.
 */
void trema_ec_bind_sample_queue(QueueHandle_t queue);

void trema_ec_unbind_sample_queue(void);

/**
 * Последний снимок из очереди (peek), если не старше max_age_ms и valid (как `trema_ph_try_cached_measurement`).
 */
bool trema_ec_try_cached_measurement(trema_ec_measurement_t *out, uint32_t max_age_ms);

/**
 * Сохранить снимок после опроса EC (`ec_node_ec_poll_sensor_once`): EC, raw, TDS ppm, stub-флаг.
 */
void trema_ec_push_telemetry_snapshot(float ec_mScm, uint16_t raw_ec_u16, bool using_stub, uint16_t tds_ppm);

bool trema_ec_init(void);
bool trema_ec_is_initialized(void);

/**
 * @brief Быстрая проверка Trema: MODEL по текущему `trema_ec_get_i2c_address()`, затем типичные адреса 0x08/0x09/0x0A.
 *        Полный перебор 1…126 — только в `trema_ec_init` (как iarduino `_begin`). Не меняет I²C-адрес драйвера.
 */
bool trema_ec_probe_present(void);

bool trema_ec_read(float *ec);

/** @see iarduino_I2C_TDS::setCalibration */
bool trema_ec_calibrate(uint8_t stage, uint16_t known_tds);

/** Синоним `trema_ec_calibrate` для соответствия имени iarduino. */
#define trema_ec_set_calibration trema_ec_calibrate

/**
 * Стадия калибровки: 0 — нет; 1 — стадия 1; 2 — стадия 2; 3 — ошибка (`TDS_BIT_CALC_ERR`).
 * @param info_out необязательно: биты `(REG_TDS_CALIBRATION & TDS_BITS_CALC_INFO) >> 2` (как в getCalibration(&info)).
 * @see iarduino_I2C_TDS::getCalibration
 */
uint8_t trema_ec_get_calibration(uint8_t *info_out);

/** Обёрка: `trema_ec_get_calibration(NULL)`. */
uint8_t trema_ec_get_calibration_status(void);

/** @see iarduino_I2C_TDS::set_t — температура жидкости 0…63.75 °C. */
bool trema_ec_set_temperature(float temperature);

#define trema_ec_set_t trema_ec_set_temperature

bool trema_ec_get_temperature(float *temperature);

/** @see iarduino_I2C_TDS::getTDS */
uint16_t trema_ec_get_tds(void);

float trema_ec_get_conductivity(void);

bool trema_ec_is_using_stub_values(void);
trema_ec_error_t trema_ec_get_error(void);

bool trema_ec_get_last_ec_register_raw(uint16_t *out_u16);

/** Текущий 7-bit адрес (после init / changeAddress). @see iarduino_I2C_TDS::getAddress */
uint8_t trema_ec_get_i2c_address(void);
#define trema_ec_get_address trema_ec_get_i2c_address

/** Версия прошивки модуля (байт REG_VERSION из блока идентификации при init). @see iarduino_I2C_TDS::getVersion */
uint8_t trema_ec_get_module_firmware_version(void);

/** @see iarduino_I2C_TDS::reset */
bool trema_ec_reset_device(void);

/**
 * @param new_addr_7bit 0x01…0x7E (запрещены 0x00 и 0x7F; как в upstream).
 * @see iarduino_I2C_TDS::changeAddress
 */
bool trema_ec_change_address(uint8_t new_addr_7bit);

/** true, если модуль поддерживает подтяжку и она включена. @see iarduino_I2C_TDS::getPullI2C */
bool trema_ec_get_pull_i2c(void);

/** @see iarduino_I2C_TDS::setPullI2C */
bool trema_ec_set_pull_i2c(bool enable);

/** @see iarduino_I2C_TDS::getFrequency */
uint16_t trema_ec_get_frequency_hz(void);

/** 50…5000 Гц. @see iarduino_I2C_TDS::setFrequency */
bool trema_ec_set_frequency_hz(uint16_t frequency_hz);

/** @see iarduino_I2C_TDS::getKnownTDS */
uint16_t trema_ec_get_known_tds(uint8_t stage_1_or_2);

/** @see iarduino_I2C_TDS::setKnownTDS */
bool trema_ec_set_known_tds(uint8_t stage_1_or_2, uint16_t tds_ppm);

float trema_ec_get_ka(void);
bool trema_ec_set_ka(float ka);

float trema_ec_get_kb(void);
bool trema_ec_set_kb(float kb);

float trema_ec_get_kt(void);
bool trema_ec_set_kt(float kt);

float trema_ec_get_kp(void);
bool trema_ec_set_kp(float kp);

/** Опорная температура T, 0…63.75 °C. @see iarduino_I2C_TDS::get_T */
float trema_ec_get_reference_temperature_c(void);

/** @see iarduino_I2C_TDS::set_T */
bool trema_ec_set_reference_temperature_c(float temperature_c);

/** @see iarduino_I2C_TDS::getRo */
uint32_t trema_ec_get_ro_ohm(void);

/** @see iarduino_I2C_TDS::getVout */
float trema_ec_get_vout_volts(void);

/** Измеренная проводимость S, мСм/см. @see iarduino_I2C_TDS::get_S */
float trema_ec_get_S_mScm(void);

/** EC с регистра (мСм/см), без логики stub/валидации `trema_ec_read`. @see iarduino_I2C_TDS::getEC */
float trema_ec_get_ec_register_mScm(void);

#ifdef __cplusplus
}
#endif

#endif
