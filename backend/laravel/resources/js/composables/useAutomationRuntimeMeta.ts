import { computed, getCurrentInstance, onMounted, onUnmounted, ref, type ComputedRef, type Ref } from 'vue'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import {
  automationHasTerminalFailure,
  automationIndicatesActiveFailure,
  automationIndicatesHistoricalFailure,
} from '@/utils/automationFailureState'
import type { AutomationState } from '@/types/Automation'

export interface AutomationRuntimeMeta {
  isStale: ComputedRef<boolean>
  dataTimestamp: ComputedRef<string | null>
  staleDuration: ComputedRef<string | null>
  hasFailed: ComputedRef<boolean>
  hasActiveFailure: ComputedRef<boolean>
  hasHistoricalFailure: ComputedRef<boolean>
  errorCode: ComputedRef<string | null>
  errorMessage: ComputedRef<string | null>
  humanErrorMessage: ComputedRef<string | null>
}

export function useAutomationRuntimeMeta(
  automationState: Ref<AutomationState | null>,
): AutomationRuntimeMeta {
  const nowMs = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | null = null

  if (getCurrentInstance()) {
    onMounted(() => {
      timer = setInterval(() => {
        nowMs.value = Date.now()
      }, 1000)
    })

    onUnmounted(() => {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    })
  }

  const isStale = computed(() => Boolean(automationState.value?.state_meta?.is_stale))

  const dataTimestamp = computed(() => {
    const servedAt = automationState.value?.state_meta?.served_at
    if (!servedAt) {
      return null
    }
    try {
      return new Date(servedAt).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return servedAt
    }
  })

  const staleDuration = computed(() => {
    if (!isStale.value) {
      return null
    }
    const servedAt = automationState.value?.state_meta?.served_at
    if (!servedAt) {
      return null
    }
    const servedAtMs = Date.parse(servedAt)
    if (!Number.isFinite(servedAtMs)) {
      return null
    }
    const elapsedSec = Math.max(0, Math.floor((nowMs.value - servedAtMs) / 1000))
    const mm = Math.floor(elapsedSec / 60)
    const ss = elapsedSec % 60
    return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
  })

  const hasActiveFailure = computed(() => automationIndicatesActiveFailure(automationState.value))

  const hasHistoricalFailure = computed(() => automationIndicatesHistoricalFailure(automationState.value))

  const hasFailed = computed(() => automationHasTerminalFailure(automationState.value))

  const errorCode = computed(() => {
    if (automationState.value?.state_details?.failed) {
      return automationState.value.state_details.error_code ?? null
    }
    return automationState.value?.last_terminal_failure?.error_code
      ?? automationState.value?.state_details?.error_code
      ?? null
  })

  const errorMessage = computed(() => {
    if (automationState.value?.state_details?.failed) {
      return automationState.value.state_details.error_message ?? null
    }
    return automationState.value?.last_terminal_failure?.error_message
      ?? automationState.value?.state_details?.error_message
      ?? null
  })

  const humanErrorMessage = computed(() => {
    if (automationState.value?.state_details?.failed) {
      return resolveHumanErrorMessage({
        code: automationState.value.state_details.error_code,
        message: automationState.value.state_details.error_message,
        humanMessage: automationState.value.state_details.human_error_message,
      })
    }

    const lastFailure = automationState.value?.last_terminal_failure
    if (lastFailure) {
      return resolveHumanErrorMessage({
        code: lastFailure.error_code,
        message: lastFailure.error_message,
        humanMessage: lastFailure.human_error_message,
      })
    }

    return resolveHumanErrorMessage({
      code: automationState.value?.state_details?.error_code,
      message: automationState.value?.state_details?.error_message,
      humanMessage: automationState.value?.state_details?.human_error_message,
    })
  })

  return {
    isStale,
    dataTimestamp,
    staleDuration,
    hasFailed,
    hasActiveFailure,
    hasHistoricalFailure,
    errorCode,
    errorMessage,
    humanErrorMessage,
  }
}
