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

  async function canAssignToZone(nodeId: number): Promise<boolean> {
    const transitions = await getAllowedTransitions(nodeId)

    if (!transitions) {
      return false
    }

    const currentState = transitions.current_state.value

    if (currentState !== 'REGISTERED_BACKEND') {
      return false
    }

    return transitions.allowed_transitions.some(
      transition => transition.value === 'ASSIGNED_TO_ZONE'
    )
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
  }
}
