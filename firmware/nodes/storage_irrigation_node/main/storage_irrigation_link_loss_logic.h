/**
 * @file storage_irrigation_link_loss_logic.h
 * @brief Решение safe-stop полива без ESP-IDF.
 *
 * По таймауту связи насос и клапаны снимаются, активная команда сбрасывается.
 * Восстановление MQTT само выходы не включает и полив не продолжает.
 * Host-тест: firmware/tests/host/test_storage_irr_link_loss.c
 */

#ifndef STORAGE_IRRIGATION_LINK_LOSS_LOGIC_H
#define STORAGE_IRRIGATION_LINK_LOSS_LOGIC_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Все каналы в false, команда полива больше не активна. */
void storage_irr_link_loss_safe_stop(bool *channel_on, size_t channel_count, bool *command_active);

/**
 * Reconnect не переводит ни один канал из false в true и не возобновляет команду.
 * Уже включенный канал (таймаут ещё не сработал) не трогается.
 */
void storage_irr_link_loss_on_link_restored(bool *channel_on, size_t channel_count, bool *command_active);

#ifdef __cplusplus
}
#endif

#endif /* STORAGE_IRRIGATION_LINK_LOSS_LOGIC_H */
