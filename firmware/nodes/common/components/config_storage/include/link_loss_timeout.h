/**
 * @file link_loss_timeout.h
 * @brief Разбор link_loss_timeout_sec без ESP-IDF.
 *
 * Нет поля — 30 с. Целое 10…300 принимается. 0, дробное, нечисло и всё вне
 * диапазона отклоняют конфиг целиком: ноль не выключает таймер и не подменяется
 * дефолтом. Host-тест: firmware/tests/host/test_storage_irr_link_loss.c
 */

#ifndef LINK_LOSS_TIMEOUT_H
#define LINK_LOSS_TIMEOUT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LINK_LOSS_TIMEOUT_SEC_MIN 10
#define LINK_LOSS_TIMEOUT_SEC_MAX 300
#define LINK_LOSS_TIMEOUT_SEC_DEFAULT 30

typedef enum {
    LINK_LOSS_TIMEOUT_ABSENT = 0,
    LINK_LOSS_TIMEOUT_VALID,
    LINK_LOSS_TIMEOUT_INVALID,
} link_loss_timeout_field_status_t;

typedef struct {
    link_loss_timeout_field_status_t status;
    int32_t value;
} link_loss_timeout_field_t;

typedef enum {
    LINK_LOSS_TIMEOUT_RESOLVE_DEFAULTED = 0,
    LINK_LOSS_TIMEOUT_RESOLVE_ACCEPTED,
    LINK_LOSS_TIMEOUT_RESOLVE_REJECTED,
} link_loss_timeout_resolve_status_t;

link_loss_timeout_field_t link_loss_timeout_field_absent(void);

/**
 * @brief Классификация одного поля.
 *
 * present=false — поля нет (ABSENT), значение игнорируется.
 * present=true и не целое 10…300 — INVALID, включая 0.
 */
link_loss_timeout_field_t link_loss_timeout_field_from_number(bool present, bool is_number, double value);

/**
 * @brief Одно правило для верхнего поля и зеркала fail_safe_guards.
 *
 * Любой INVALID или два разных VALID — REJECTED, *out_sec не пишется.
 * Оба ABSENT — DEFAULTED и 30. Иначе ACCEPTED: верхнее поле, если оно есть,
 * иначе зеркало.
 */
link_loss_timeout_resolve_status_t link_loss_timeout_resolve(
    link_loss_timeout_field_t top,
    link_loss_timeout_field_t guards,
    uint32_t *out_sec
);

#ifdef __cplusplus
}
#endif

#endif /* LINK_LOSS_TIMEOUT_H */
