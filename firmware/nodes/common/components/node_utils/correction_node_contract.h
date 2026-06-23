/**
 * @file correction_node_contract.h
 * @brief Общие константы контракта для correction-нод (ph_node, ec_node)
 *
 * Единый источник для pump queue, лимитов run_pump и периода STATUS.
 */

#ifndef CORRECTION_NODE_CONTRACT_H
#define CORRECTION_NODE_CONTRACT_H

#ifdef __cplusplus
extern "C" {
#endif

/** Глубина очереди run_pump/dose (ph_node, ec_node). */
#define CORRECTION_NODE_PUMP_QUEUE_MAX 8U

/** Верхняя граница duration_ms в команде run_pump (мс). */
#define CORRECTION_NODE_RUN_PUMP_DURATION_MAX_MS 60000U

/** Дефолт max_duration_ms в channel map / safe_limits actuator. */
#define CORRECTION_NODE_ACTUATOR_MAX_DURATION_MS CORRECTION_NODE_RUN_PUMP_DURATION_MAX_MS

/** Период публикации STATUS (DEVICE_NODE_PROTOCOL.md). */
#define CORRECTION_NODE_STATUS_PUBLISH_INTERVAL_MS 60000U

#ifdef __cplusplus
}
#endif

#endif // CORRECTION_NODE_CONTRACT_H
