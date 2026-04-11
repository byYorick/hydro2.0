import { onMounted, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import type { AutomationLogicMode } from '@/composables/zoneAutomationUtils'
import {
  normalizeAutomationControlMode,
  normalizeAutomationManualSteps,
} from '@/composables/zoneAutomationUtils'
import { useWebSocket } from '@/composables/useWebSocket'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import type { AutomationControlMode, AutomationManualStep, AutomationState } from '@/types/Automation'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'

export interface ZoneAutomationSchedulerDeps {
  showToast: ToastHandler
}

export function useZoneAutomationScheduler(props: ZoneAutomationTabProps, deps: ZoneAutomationSchedulerDeps) {
  const { showToast } = deps
  const { subscribeToZoneCommands, unsubscribeAll } = useWebSocket(
    showToast,
    'zone-automation-runtime'
  )

  const automationControlMode = ref<AutomationControlMode>('auto')
  const allowedManualSteps = ref<AutomationManualStep[]>([])
  const automationControlModeLoading = ref(false)
  const automationControlModeSaving = ref(false)
  const manualStepLoading = ref<Record<AutomationManualStep, boolean>>({
    clean_fill_start: false,
    clean_fill_stop: false,
    solution_fill_start: false,
    solution_fill_stop: false,
    prepare_recirculation_start: false,
    prepare_recirculation_stop: false,
    irrigation_stop: false,
    irrigation_recovery_start: false,
    irrigation_recovery_stop: false,
  })

  let refreshInFlight = false
  let unsubscribeZoneCommands: (() => void) | null = null
  let unsubscribeZoneEvents: (() => void) | null = null

  function extractApiErrorMessage(error: unknown, fallback: string): string {
    const err = error as { response?: { data?: unknown } }
    const data = err?.response?.data
    if (typeof data === 'string' && data.trim() !== '') {
      return data.trim()
    }

    if (data && typeof data === 'object') {
      const payload = data as Record<string, unknown>
      for (const key of ['message', 'error', 'code', 'detail'] as const) {
        const value = payload[key]
        if (typeof value === 'string' && value.trim() !== '') {
          return value.trim()
        }
      }
    }

    return fallback
  }

  function syncControlModeFromAutomationState(snapshot: AutomationState | null): void {
    if (!snapshot || automationControlModeSaving.value) {
      return
    }

    automationControlMode.value = normalizeAutomationControlMode(snapshot.control_mode)
    allowedManualSteps.value = normalizeAutomationManualSteps(snapshot.allowed_manual_steps)
  }

  async function fetchAutomationControlMode(): Promise<void> {
    if (!props.zoneId) {
      automationControlMode.value = 'auto'
      allowedManualSteps.value = []
      automationControlModeLoading.value = false
      return
    }

    const requestedZoneId = props.zoneId
    automationControlModeLoading.value = true
    try {
      const response = await api.zones.getControlMode<{ data?: { control_mode?: string; allowed_manual_steps?: unknown[] }; control_mode?: string; allowed_manual_steps?: unknown[] }>(
        requestedZoneId
      )
      if (props.zoneId !== requestedZoneId) return

      const payload = response?.data ?? response ?? {}
      automationControlMode.value = normalizeAutomationControlMode(payload.control_mode)
      allowedManualSteps.value = normalizeAutomationManualSteps(payload.allowed_manual_steps)
    } catch (error) {
      if (props.zoneId !== requestedZoneId) return
      logger.warn('[ZoneAutomationTab] Failed to fetch automation control mode', { error, zoneId: requestedZoneId })
      automationControlMode.value = 'auto'
      allowedManualSteps.value = []
    } finally {
      if (props.zoneId === requestedZoneId) {
        automationControlModeLoading.value = false
      }
    }
  }

  async function setAutomationControlMode(mode: AutomationControlMode): Promise<boolean> {
    if (!props.zoneId) return false

    automationControlModeSaving.value = true
    try {
      const response = await api.zones.setControlMode<{ data?: { control_mode?: string; allowed_manual_steps?: unknown[] }; control_mode?: string; allowed_manual_steps?: unknown[] }>(
        props.zoneId,
        {
          control_mode: mode,
          source: 'frontend',
        }
      )

      const payload = response?.data ?? response ?? {}
      automationControlMode.value = normalizeAutomationControlMode(payload.control_mode ?? mode)
      allowedManualSteps.value = normalizeAutomationManualSteps(payload.allowed_manual_steps)
      showToast('Режим управления автоматикой обновлён.', 'success')
      return true
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to update automation control mode', { error, zoneId: props.zoneId, mode })
      showToast(extractApiErrorMessage(error, 'Не удалось обновить режим управления.'), 'error')
      return false
    } finally {
      automationControlModeSaving.value = false
    }
  }

  async function runManualStep(step: AutomationManualStep): Promise<void> {
    if (!props.zoneId) return

    manualStepLoading.value[step] = true
    try {
      await api.zones.runManualStep(props.zoneId, {
        manual_step: step,
        source: 'frontend_manual_step',
      })
      showToast('Команда manual-step отправлена.', 'success')
      await fetchAutomationControlMode()
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to run manual step', { error, zoneId: props.zoneId, step })
      showToast(extractApiErrorMessage(error, 'Не удалось выполнить manual-step.'), 'error')
    } finally {
      manualStepLoading.value[step] = false
    }
  }

  async function refreshRuntimeState(): Promise<void> {
    if (!props.zoneId || refreshInFlight) return

    refreshInFlight = true
    try {
      await fetchAutomationControlMode()
    } finally {
      refreshInFlight = false
    }
  }

  function stopRealtimeSubscriptions(): void {
    if (unsubscribeZoneCommands) {
      unsubscribeZoneCommands()
      unsubscribeZoneCommands = null
    }
    if (unsubscribeZoneEvents) {
      unsubscribeZoneEvents()
      unsubscribeZoneEvents = null
    }
  }

  function startRealtimeSubscriptions(): void {
    stopRealtimeSubscriptions()
    if (!props.zoneId) return
    if (import.meta.env.MODE === 'test') return

    unsubscribeZoneCommands = subscribeToZoneCommands(props.zoneId, () => {
      void refreshRuntimeState()
    })

    unsubscribeZoneEvents = subscribeManagedChannelEvents({
      channelName: `hydro.zones.${props.zoneId}`,
      componentTag: `zone-automation-runtime:events:${props.zoneId}`,
      eventHandlers: {
        '.EventCreated': (payload) => {
          const kind = String(payload.kind ?? '').trim().toUpperCase()
          if (
            kind === 'AUTOMATION_CONTROL_MODE_UPDATED'
            || kind.startsWith('MANUAL_STEP_')
            || kind.startsWith('COMMAND_')
          ) {
            void refreshRuntimeState()
          }
        },
        '.App\\Events\\EventCreated': (payload) => {
          const kind = String(payload.kind ?? '').trim().toUpperCase()
          if (
            kind === 'AUTOMATION_CONTROL_MODE_UPDATED'
            || kind.startsWith('MANUAL_STEP_')
            || kind.startsWith('COMMAND_')
          ) {
            void refreshRuntimeState()
          }
        },
      },
    })
  }

  function resetForZoneChange(): void {
    automationControlMode.value = 'auto'
    allowedManualSteps.value = []
    automationControlModeLoading.value = false
    automationControlModeSaving.value = false
    refreshInFlight = false
    for (const step of Object.keys(manualStepLoading.value) as AutomationManualStep[]) {
      manualStepLoading.value[step] = false
    }
  }

  onMounted(() => {
    startRealtimeSubscriptions()
  })

  onUnmounted(() => {
    stopRealtimeSubscriptions()
    unsubscribeAll()
  })

  watch(
    () => props.zoneId,
    () => {
      startRealtimeSubscriptions()
    }
  )

  return {
    automationControlMode,
    allowedManualSteps,
    automationControlModeLoading,
    automationControlModeSaving,
    manualStepLoading,
    fetchAutomationControlMode,
    setAutomationControlMode,
    syncControlModeFromAutomationState,
    runManualStep,
    resetForZoneChange,
    formatDateTime: (value: string | null | undefined) => {
      if (!value) return '—'
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) return String(value)
      return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date)
    },
  }
}

export type { AutomationLogicMode }
