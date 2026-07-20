/**
 * Composable для работы с lifecycle переходами узлов
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import { logger } from '@/utils/logger'
import { useErrorHandler } from './useErrorHandler'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

export type NodeLifecycleState =
  | 'MANUFACTURED'
  | 'UNPROVISIONED'
  | 'PROVISIONED_WIFI'
  | 'REGISTERED_BACKEND'
  | 'ASSIGNED_TO_ZONE'
  | 'ACTIVE'
  | 'DEGRADED'
  | 'MAINTENANCE'
  | 'DECOMMISSIONED'

/**
 * Состояния, из которых backend NodeService допускает UI bind/rebind
 * (через pending_zone_id). DEGRADED/MAINTENANCE — нет (см. NodeService).
 */
export const ASSIGNABLE_LIFECYCLE_STATES: readonly NodeLifecycleState[] = [
  'REGISTERED_BACKEND',
  'ASSIGNED_TO_ZONE',
  'ACTIVE',
] as const

export interface AllowedTransition {
  value: NodeLifecycleState
  label: string
  can_receive_telemetry: boolean
  is_active: boolean
}

export interface CurrentState {
  value: NodeLifecycleState
  label: string
  can_receive_telemetry: boolean
  is_active: boolean
}

export interface AllowedTransitionsResponse {
  current_state: CurrentState
  allowed_transitions: AllowedTransition[]
}

interface TransitionNodeResponse {
  node: unknown
  previous_state: string | null
  current_state: string | null
}

export function isAssignableLifecycleState(
  state: NodeLifecycleState | string | null | undefined
): boolean {
  if (!state) {
    return false
  }

  return (ASSIGNABLE_LIFECYCLE_STATES as readonly string[]).includes(state)
}

/**
 * Rebind confirm: узел уже стабильно привязан (zone_id) или в assigned/active lifecycle.
 */
export function needsRebindConfirm(node: {
  zone_id?: number | null
  lifecycle_state?: string | null
}): boolean {
  if (node.zone_id) {
    return true
  }

  return node.lifecycle_state === 'ASSIGNED_TO_ZONE' || node.lifecycle_state === 'ACTIVE'
}

/** Возраст pending bind для операторского UX (null если timestamp нет/невалиден). */
export function formatPendingBindAge(iso: string | null | undefined): string | null {
  if (!iso) {
    return null
  }

  const setAt = new Date(iso)
  if (Number.isNaN(setAt.getTime())) {
    return null
  }

  const minutes = Math.max(0, Math.floor((Date.now() - setAt.getTime()) / 60_000))
  if (minutes < 1) {
    return 'только что'
  }
  if (minutes < 60) {
    return `${minutes} мин`
  }

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours} ч`
  }

  return `${Math.floor(hours / 24)} д`
}

export function useNodeLifecycle(showToast?: ToastHandler) {
  const { handleError } = useErrorHandler(showToast || null)

  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  async function transitionNode(
    nodeId: number,
    targetState: NodeLifecycleState,
    reason?: string
  ): Promise<TransitionNodeResponse | null> {
    loading.value = true
    error.value = null

    try {
      const data = await api.nodes.lifecycleTransition<TransitionNodeResponse>(nodeId, {
        target_state: targetState,
        reason,
      })

      if (!data) {
        throw new Error('Empty transition response')
      }

      logger.info(`[useNodeLifecycle] Node ${nodeId} transitioned to ${targetState}`, {
        previous_state: data.previous_state,
        current_state: data.current_state,
        reason,
      })

      if (showToast) {
        showToast(`Узел переведен в состояние: ${getStateLabel(targetState)}`, 'success', TOAST_TIMEOUT.NORMAL)
      }

      return data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || 'Ошибка перехода lifecycle'

      logger.error(`[useNodeLifecycle] Failed to transition node ${nodeId}:`, err)

      handleError(err, {
        component: 'useNodeLifecycle',
        action: 'transitionNode',
        nodeId,
        targetState,
      })

      return null
    } finally {
      loading.value = false
    }
  }

  async function getAllowedTransitions(nodeId: number): Promise<AllowedTransitionsResponse | null> {
    loading.value = true
    error.value = null

    try {
      const data = await api.nodes.getLifecycleAllowedTransitions<AllowedTransitionsResponse>(nodeId)

      if (!data) {
        throw new Error('Empty allowed transitions response')
      }

      logger.debug(`[useNodeLifecycle] Allowed transitions for node ${nodeId}:`, data.allowed_transitions.length)

      return data
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || 'Ошибка получения разрешенных переходов'

      logger.error(`[useNodeLifecycle] Failed to get allowed transitions for node ${nodeId}:`, err)

      handleError(err, {
        component: 'useNodeLifecycle',
        action: 'getAllowedTransitions',
        nodeId,
      })

      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Проверка возможности UI bind/rebind.
   * Канон = NodeService: REGISTERED_BACKEND | ASSIGNED_TO_ZONE | ACTIVE.
   * Не требует allowed transition ASSIGNED_TO_ZONE (rebind идёт через pending → REGISTERED).
   */
  async function canAssignToZone(nodeId: number): Promise<boolean> {
    const transitions = await getAllowedTransitions(nodeId)

    if (!transitions) {
      return false
    }

    return isAssignableLifecycleState(transitions.current_state.value)
  }

  function getStateLabel(state: NodeLifecycleState): string {
    const labels: Record<NodeLifecycleState, string> = {
      MANUFACTURED: 'Произведён',
      UNPROVISIONED: 'Не настроен',
      PROVISIONED_WIFI: 'Wi-Fi настроен',
      REGISTERED_BACKEND: 'Зарегистрирован',
      ASSIGNED_TO_ZONE: 'Привязан к зоне',
      ACTIVE: 'Активен',
      DEGRADED: 'С проблемами',
      MAINTENANCE: 'Обслуживание',
      DECOMMISSIONED: 'Списан',
    }

    return labels[state] || state
  }

  return {
    loading: computed(() => loading.value) as ComputedRef<boolean>,
    error: computed(() => error.value) as ComputedRef<string | null>,
    transitionNode,
    getAllowedTransitions,
    canAssignToZone,
    getStateLabel,
    isAssignableLifecycleState,
    needsRebindConfirm,
    formatPendingBindAge,
  }
}
