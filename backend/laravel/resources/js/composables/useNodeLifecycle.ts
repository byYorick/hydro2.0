/**
 * Composable для работы с lifecycle переходами узлов
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { logger } from '@/utils/logger'
import { useErrorHandler } from './useErrorHandler'
import { extractData } from '@/utils/apiHelpers'
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

export function useNodeLifecycle(showToast?: ToastHandler) {
  const { post, get } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast || null)
  
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  /**
   * Переход узла в указанное lifecycle состояние
   */
  async function transitionNode(
    nodeId: number,
    targetState: NodeLifecycleState,
    reason?: string
  ): Promise<{ node: any; previous_state: string | null; current_state: string | null } | null> {
    loading.value = true
    error.value = null
    
    try {
      const response = await post(`/api/nodes/${nodeId}/lifecycle/transition`, {
        target_state: targetState,
        reason,
      })
      
      const data = extractData(response.data)
      
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

  /**
   * Получить разрешенные переходы для узла
   */
  async function getAllowedTransitions(nodeId: number): Promise<AllowedTransitionsResponse | null> {
    loading.value = true
    error.value = null
    
    try {
      const response = await get(`/api/nodes/${nodeId}/lifecycle/allowed-transitions`)
      
      const data = extractData(response.data)
      
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
   * Проверить, может ли узел быть присвоен к зоне
   */
  async function canAssignToZone(nodeId: number): Promise<boolean> {
    const transitions = await getAllowedTransitions(nodeId)
    
    if (!transitions) {
      return false
    }
    
    // Проверяем, что текущее состояние позволяет переход к ASSIGNED_TO_ZONE
    const currentState = transitions.current_state.value
    
    // Узел должен быть в состоянии REGISTERED_BACKEND для присвоения к зоне
    if (currentState !== 'REGISTERED_BACKEND') {
      return false
    }
    
    // Проверяем, что переход к ASSIGNED_TO_ZONE разрешен
    return transitions.allowed_transitions.some(
      transition => transition.value === 'ASSIGNED_TO_ZONE'
    )
  }

  /**
   * Получить человекочитаемую метку состояния
   */
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
