/**
 * @file estop_lock_policy.h
 * @brief Политика E-STOP, не зависящая от мьютекса актуаторов.
 *
 * Контракт SAF-01: таймаут или отсутствие g_actuator_mutex не может отменить
 * обесточивание. Аргумент lock в эту функцию намеренно не входит.
 */

#ifndef ESTOP_LOCK_POLICY_H
#define ESTOP_LOCK_POLICY_H

#include <stdbool.h>

static inline bool estop_transition_requires_deenergize(bool pressed, bool latched, bool sync_pending)
{
    return pressed || latched || sync_pending;
}

/** Таймаут мьютекса никогда не разрешает пропустить de-energize. */
static inline bool estop_lock_failure_may_skip_deenergize(void)
{
    return false;
}

#endif /* ESTOP_LOCK_POLICY_H */
