/**
 * @file storage_irrigation_link_loss_logic.c
 * @brief Safe-stop storage_irrigation при потере связи: всё OFF, без автопродолжения.
 */

#include "storage_irrigation_link_loss_logic.h"

void storage_irr_link_loss_safe_stop(bool *channel_on, size_t channel_count, bool *command_active)
{
    size_t i;

    if (channel_on != NULL) {
        for (i = 0; i < channel_count; i++) {
            channel_on[i] = false;
        }
    }
    if (command_active != NULL) {
        *command_active = false;
    }
}

void storage_irr_link_loss_on_link_restored(bool *channel_on, size_t channel_count, bool *command_active)
{
    (void)channel_on;
    (void)channel_count;
    if (command_active != NULL) {
        *command_active = false;
    }
}
