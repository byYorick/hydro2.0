/**
 * @file dose_limit_node.h
 * @brief NVS и NodeConfig вокруг dose_limit для ph_node и ec_node.
 *
 * Журнал лежит в NVS namespace `dose_ledger`, ключ `win`. Запись делается
 * до пуска насоса. Ошибка записи или битый blob — доза не начинается.
 * Ребут читает тот же blob: сумма не обнуляется и не прибавляется второй раз.
 * Пока время не синхронизировано, reserve отказывает и blob не переписывает.
 */

#ifndef DOSE_LIMIT_NODE_H
#define DOSE_LIMIT_NODE_H

#include "dose_limit.h"

#include "cJSON.h"
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    DOSE_LIMIT_NODE_PH = 1,
    DOSE_LIMIT_NODE_EC = 2,
} dose_limit_node_kind_t;

/** Привязать каналы ноды, прочитать журнал и лимиты из сохранённого NodeConfig. */
esp_err_t dose_limit_node_boot(dose_limit_node_kind_t kind);

/** Обновить лимиты из уже принятого NodeConfig. Корзины не стирает. */
esp_err_t dose_limit_node_apply_config(const cJSON *config);

/**
 * Зарезервировать полную дозу. ESP_OK только если pump_allowed и blob записан.
 * Иначе насос включать нельзя.
 */
esp_err_t dose_limit_node_reserve(
    const char *channel,
    double requested_ml,
    bool time_synced,
    int64_t now_sec,
    dose_limit_result_t *out
);

/** Снять резерв, если команда не попала в очередь насоса, и переписать blob. */
esp_err_t dose_limit_node_rollback(const char *channel, double requested_ml, int64_t now_sec);

cJSON *dose_limit_result_details(const dose_limit_result_t *result);

esp_err_t dose_limit_node_write_refusal(
    const char *cmd_id,
    const dose_limit_result_t *limit,
    cJSON **response
);

#ifdef __cplusplus
}
#endif

#endif /* DOSE_LIMIT_NODE_H */
