/**
 * @file trema_ph.h
 * @brief Драйвер Trema pH (iarduino I²C Flash) для ESP-IDF / FreeRTOS
 *
 * Порт протокола библиотеки **iarduino_I2C_pH** v1.2.3 на C для hydro2.0:
 * - Оригинал (Arduino): `firmware/nodes/common/components/sensors/trema_ph/reference/iarduino_I2C_pH-1.2.3/`
 * - Архив тега: https://github.com/tremaru/iarduino_I2C_pH/archive/refs/tags/1.2.3.zip
 * - Wiki API/регистры: https://wiki.iarduino.ru/page/ph-i2c/
 *
 * Поведение init: по умолчанию **TREMA_PH_INIT_SOFTWARE_RESET=1** — после probe выполняется программный
 * reset модуля, как в `iarduino_I2C_pH::_begin` → `reset()` (см. группу макросов внизу файла).
 * Потокобезопасность: все публичные вызовы сериализуются recursive mutex (одна задача может
 * вложенно вызывать API; разные задачи — по очереди). I²C к шине 1 уже защищён `i2c_bus`.
 * Опционально: привязка `QueueHandle_t` глубины 1 — последний валидный снимок после
 * `trema_ph_read()` (см. `trema_ph_bind_sample_queue`).
 */

#ifndef TREMA_PH_H
#define TREMA_PH_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

/** 7-bit адрес по умолчанию (wiki iarduino FLASH-I2C pH); 0x0A — встречается у части плат */
#define TREMA_PH_ADDR 0x09

/** Идентификатор модели и линейки чипа — как в `iarduino_I2C_pH.h` v1.2.3 */
#define TREMA_PH_MODEL_ID       0x1A
#define TREMA_PH_CHIP_ID_FLASH  0x3C
#define TREMA_PH_CHIP_ID_METRO  0xC3

/*
 * Регистры модуля (имена и адреса — из iarduino_I2C_pH.h v1.2.3).
 * Старые макросы REG_* оставлены как алиасы для совместимости с существующим кодом.
 */
#define TREMA_PH_REG_FLAGS_0        0x00
#define TREMA_PH_REG_BITS_0         0x01
#define TREMA_PH_REG_FLAGS_1        0x02
#define TREMA_PH_REG_BITS_1         0x03
#define TREMA_PH_REG_MODEL          0x04
#define TREMA_PH_REG_VERSION        0x05
#define TREMA_PH_REG_ADDRESS        0x06
#define TREMA_PH_REG_CHIP_ID        0x07
#define TREMA_PH_REG_PH_KNOWN_PH    0x0A
#define TREMA_PH_REG_PH_KNOWN_PH_1  0x0C
#define TREMA_PH_REG_PH_KNOWN_PH_2  0x0E
#define TREMA_PH_REG_PH_CALIBRATION 0x10
#define TREMA_PH_REG_PH_Ky          0x11
#define TREMA_PH_REG_PH_Ustp        0x13
#define TREMA_PH_REG_PH_pHn         0x15
#define TREMA_PH_REG_PH_Uin         0x17
#define TREMA_PH_REG_PH_Uout        0x19
#define TREMA_PH_REG_PH_Un          0x1B
#define TREMA_PH_REG_PH_pH          0x1D
#define TREMA_PH_REG_PH_ERROR       0x1F

#define REG_PH_KNOWN_PH     TREMA_PH_REG_PH_KNOWN_PH
#define REG_PH_CALIBRATION  TREMA_PH_REG_PH_CALIBRATION
#define REG_PH_pH           TREMA_PH_REG_PH_pH
#define REG_PH_ERROR        TREMA_PH_REG_PH_ERROR
#define REG_MODEL           TREMA_PH_REG_MODEL

/** REG_PH_ERROR */
#define PH_FLG_STAB_ERR     0x02
#define PH_FLG_CALC_ERR     0x01

/** REG_PH_CALIBRATION */
#define PH_FLG_STATUS_1    0x40
#define PH_FLG_STATUS_2    0x80
#define PH_BIT_CALC_1       0x01
#define PH_BIT_CALC_2       0x02
#define PH_CODE_CALC_SAVE   0x24

/** REG_FLAGS_0: модуль поддерживает управление подтяжкой I²C (см. getPullI2C в iarduino) */
#define TREMA_PH_FLG_I2C_UP 0x04
/** REG_BITS_0: включение подтяжки линий I²C на модуле */
#define TREMA_PH_BIT_I2C_UP 0x04
/** REG_BITS_0: блокировка смены адреса */
#define TREMA_PH_BIT_BLOCK_ADR 0x08
/** Разрешить запись нового адреса во flash */
#define TREMA_PH_BIT_SAVE_ADR_EN 0x02

/**
 * @defgroup trema_ph_build_flags Флаги сборки (parity с iarduino_I2C_pH v1.2.3)
 *
 * Переопределение: в `CMakeLists.txt` потребителя или через `idf.py build`
 * добавьте `target_compile_definitions(... PRIVATE TREMA_PH_INIT_SOFTWARE_RESET=0)`.
 * @{
 */

/**
 * После успешного probe в trema_ph_init выполнять программный reset модуля (бит SET_RESET в
 * REG_BITS_0, ожидание FLG_RESET, переинициализация I²C), затем паузу TREMA_PH_POST_INIT_RESET_MS.
 * Эквивалентно цепочке iarduino_I2C_pH::_begin() → reset() → delay(5).
 *
 * Значение 0: не сбрасывать регистры модуля в default при init (быстрее старт; отличие от Arduino API).
 */
#ifndef TREMA_PH_INIT_SOFTWARE_RESET
#define TREMA_PH_INIT_SOFTWARE_RESET 1
#endif

/** Пауза после программного reset при init (мс); в iarduino после reset — delay(5). */
#ifndef TREMA_PH_POST_INIT_RESET_MS
#define TREMA_PH_POST_INIT_RESET_MS 5
#endif

/**
 * В trema_ph_read: вторая фаза с soft reset при «сыром» значении 0xFFFF и дополнительные попытки.
 * Не входит в оригинальный getPH(); опциональное усиление устойчивости к сбоям шины.
 */
#ifndef TREMA_PH_READ_SOFT_RESET_RECOVERY
#define TREMA_PH_READ_SOFT_RESET_RECOVERY 0
#endif

/** @} */

/**
 * @brief Снимок измерения для телеметрии / очереди (без указателей — копируется целиком).
 */
typedef struct {
    float ph;
    uint16_t raw_thousandths;
    uint8_t error_flags;
    bool stable;
    bool valid;
    TickType_t tick_stamp;
} trema_ph_measurement_t;

void trema_ph_set_i2c_address(uint8_t addr_7bit);
uint8_t trema_ph_get_i2c_address(void);

/**
 * @brief Привязать очередь глубины 1, sizeof(trema_ph_measurement_t).
 *
 * После каждого успешного `trema_ph_read()` выполняется xQueueOverwrite (нужна глубина ровно 1).
 * Утечек нет: очередь создаёт и владеет ею вызывающий код.
 */
void trema_ph_bind_sample_queue(QueueHandle_t queue);

/** Снять привязку очереди (например перед vQueueDelete). */
void trema_ph_unbind_sample_queue(void);

/**
 * @brief Взять последний снимок из очереди без удаления (peek).
 *
 * @param out куда записать
 * @param max_age_ms максимальный возраст снимка с момента trema_ph_read()
 * @return true если в очереди есть свежий valid снимок
 */
bool trema_ph_try_cached_measurement(trema_ph_measurement_t *out, uint32_t max_age_ms);

uint8_t trema_ph_get_firmware_version(void);

bool trema_ph_init(void);
bool trema_ph_read(float *ph);

/**
 * @brief Калибровка (как setCalibration + ожидание idle в прошивке; расширение относительно Arduino).
 *
 * Соответствует `iarduino_I2C_pH::setCalibration` + опрос статуса до завершения этапа.
 */
bool trema_ph_calibrate(uint8_t stage, float known_pH);

uint8_t trema_ph_get_calibration_status(void);
bool trema_ph_get_calibration_result(void);
bool trema_ph_get_stability(void);
bool trema_ph_get_last_read_stability(void);
bool trema_ph_wait_for_stable_reading(uint32_t timeout_ms);
float trema_ph_get_value(void);

/** Как `iarduino_I2C_pH::reset` — soft reset модуля; при необходимости сброс FSM мастера I²C шины 1 */
bool trema_ph_reset(void);

bool trema_ph_is_using_stub_values(void);
bool trema_ph_is_initialized(void);
bool trema_ph_log_connection_status(void);
bool trema_ph_probe_presence(void);
void trema_ph_set_read_trace_verbose(bool verbose);

/* --- Функции из iarduino_I2C_pH v1.2.3 (имена в стиле trema_ph_*) --- */

/** changeAddress: новый 7-bit адрес (запрещены 0x00 и 0x7F, см. оригинал). */
bool trema_ph_change_i2c_address(uint8_t new_addr_7bit);

/** getPullI2C / setPullI2C */
bool trema_ph_get_pull_i2c(bool *pull_enabled_out);
bool trema_ph_set_pull_i2c(bool enable);

/** getKnownPH / setKnownPH — буферные pH для калибровки «с кнопки» (регистры 0x0C / 0x0E). */
float trema_ph_get_known_ph(uint8_t stage);
bool trema_ph_set_known_ph(uint8_t stage, float known_ph);

/** getKy / setKy — коэффициент усиления, 1..65.535 в тысячных */
float trema_ph_get_ky(void);
bool trema_ph_set_ky(float ky);

/** getVstp / setVstp — шаг Ustp в сотых долях мВ на 1 pH (0.01..655.35 мВ) */
float trema_ph_get_vstp(void);
bool trema_ph_set_vstp(float vstp_mv);

/** Напряжения в вольтах (десятитысячные доли В в модуле) */
float trema_ph_get_u_in(void);
float trema_ph_get_u_out(void);
float trema_ph_get_u_n(void);

/** getPHn / setPHn — нейтральный pH датчика в тысячных */
float trema_ph_get_phn(void);
bool trema_ph_set_phn(float phn);

#ifdef __cplusplus
}
#endif

#endif // TREMA_PH_H
