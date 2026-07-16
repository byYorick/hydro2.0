import { onMounted, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import type { AutomationLogicMode } from '@/composables/zoneAutomationUtils'
import {
  hasExplicitControlMode,
  normalizeAutomationControlMode,
  normalizeAutomationControlModes,
  normalizeAutomationManualSteps,
  resolveAllowedManualSteps,
} from '@/composables/zoneAutomationUtils'
import { useWebSocket } from '@/composables/useWebSocket'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import type { AutomationControlMode, AutomationManualStep, AutomationState } from '@/types/Automation'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import { extractHumanErrorMessage } from '@/utils/errorMessage'

export interface ZoneAutomationSchedulerDeps {
  showToast: ToastHandler
  onControlModeChanged?: () => void
}

type ControlModePayload = {
  control_mode?: string
  allowed_manual_steps?: unknown
  available_modes?: unknown
  control_mode_available?: unknown
  current_stage?: string | null
  data?: ControlModePayload
}

function parseControlModePayload(raw: unknown): {
  control_mode: AutomationControlMode
  allowed_manual_steps: AutomationManualStep[]
  control_mode_available: AutomationControlMode[]
  current_stage: string | null
} {
  const payload = (raw && typeof raw === 'object' ? raw : {}) as ControlModePayload
  const nested = payload.data && typeof payload.data === 'object'
    ? (payload.data as ControlModePayload)
    : null
  const source = nested ?? payload
  const controlMode = normalizeAutomationControlMode(source.control_mode)
  const currentStage = typeof source.current_stage === 'string' && source.current_stage.trim() !== ''
    ? source.current_stage.trim()
    : null

  return {
    control_mode: controlMode,
    allowed_manual_steps: resolveAllowedManualSteps(
      controlMode,
      currentStage,
      normalizeAutomationManualSteps(source.allowed_manual_steps),
    ),
    control_mode_available: normalizeAutomationControlModes(
      source.control_mode_available ?? source.available_modes,
    ),
    current_stage: currentStage,
  }
}

export function useZoneAutomationScheduler(props: ZoneAutomationTabProps, deps: ZoneAutomationSchedulerDeps) {
  const { showToast, onControlModeChanged } = deps
  const { subscribeToZoneCommands, unsubscribeAll } = useWebSocket(
    showToast,
    'zone-automation-runtime'
  )

  const automationControlMode = ref<AutomationControlMode>('auto')
  const controlModeAvailable = ref<AutomationControlMode[]>(['auto', 'semi', 'manual'])
  const allowedManualSteps = ref<AutomationManualStep[]>([])
  const automationCurrentStage = ref<string | null>(null)
  const automationControlModeLoading = ref(false)
  const automationControlModeSaving = ref(false)
  const manualStepLoading = ref<Record<AutomationManualStep, boolean>>({
    clean_fill_start: false,
    clean_fill_stop: false,
    solution_fill_start: false,
    force_solution_fill_start: false,
    solution_fill_stop: false,
    prepare_recirculation_stop: false,
    irrigation_stop: false,
    irrigation_recovery_stop: false,
    solution_drain_confirm: false,
    solution_refill_confirm: false,
    solution_change_abort: false,
  })

  let refreshInFlight = false
  let refreshQueued = false
  let refreshGeneration = 0
  let unsubscribeZoneCommands: (() => void) | null = null
  let unsubscribeZoneEvents: (() => void) | null = null

  function hydrateControlModeFromProp(): void {
    if (!hasExplicitControlMode(props.zoneControlMode)) {
      return
    }
    automationControlMode.value = normalizeAutomationControlMode(props.zoneControlMode)
  }

  function syncControlModeFromAutomationState(snapshot: AutomationState | null): void {
    if (!snapshot || automationControlModeSaving.value) {
      return
    }

    // Не перезаписываем режим, если /state не вернул control_mode (иначе скачок auto↔semi).
    if (snapshot.control_mode === undefined) {
      return
    }

    automationControlMode.value = snapshot.control_mode
    if (snapshot.current_stage !== undefined) {
      automationCurrentStage.value = snapshot.current_stage
    }
    const previousStage = automationCurrentStage.value
    const resolvedSteps = resolveAllowedManualSteps(
      snapshot.control_mode,
      snapshot.current_stage,
      snapshot.allowed_manual_steps,
    )
    // Preserve only when /state omitted allowed_manual_steps entirely (legacy).
    // Explicit [] after solution_change must clear ghost gate buttons.
    const stepsOmitted = snapshot.allowed_manual_steps === undefined
    const stageChanged = previousStage !== undefined
      && previousStage !== snapshot.current_stage
    if (
      stepsOmitted
      && resolvedSteps.length === 0
      && allowedManualSteps.value.length > 0
      && snapshot.control_mode === 'auto'
      && !stageChanged
    ) {
      // keep existing gate steps until control-mode/state catches up
    } else {
      allowedManualSteps.value = resolvedSteps
    }
    if (snapshot.control_mode_available !== undefined && snapshot.control_mode_available.length > 0) {
      controlModeAvailable.value = snapshot.control_mode_available
    }
  }

  function applyControlModePayload(raw: unknown): void {
    const parsed = parseControlModePayload(raw)
    automationControlMode.value = parsed.control_mode
    automationCurrentStage.value = parsed.current_stage
    allowedManualSteps.value = parsed.allowed_manual_steps
    if (parsed.control_mode_available.length > 0) {
      controlModeAvailable.value = parsed.control_mode_available
    }
  }

  async function fetchAutomationControlMode(): Promise<void> {
    if (!props.zoneId) {
      if (!hasExplicitControlMode(props.zoneControlMode)) {
        automationControlMode.value = 'auto'
      } else {
        hydrateControlModeFromProp()
      }
      allowedManualSteps.value = []
      automationCurrentStage.value = null
      automationControlModeLoading.value = false
      return
    }

    const requestedZoneId = props.zoneId
    automationControlModeLoading.value = true
    try {
      const response = await api.zones.getControlMode<unknown>(requestedZoneId)
      if (props.zoneId !== requestedZoneId) return

      applyControlModePayload(response)
    } catch (error) {
      if (props.zoneId !== requestedZoneId) return
      logger.warn('[ZoneAutomationTab] Failed to fetch automation control mode', { error, zoneId: requestedZoneId })
      // Не сбрасываем в auto при transient 503 — иначе скачок semi↔auto.
      // allowed_manual_steps не сбрасываем — state snapshot мог уже заполнить список.
    } finally {
      if (props.zoneId === requestedZoneId) {
        automationControlModeLoading.value = false
      }
    }
  }

  async function setAutomationControlMode(mode: AutomationControlMode, reason?: string): Promise<boolean> {
    if (!props.zoneId) return false

    automationControlModeSaving.value = true
    try {
      const body: { control_mode: AutomationControlMode; source?: string; reason?: string } = {
        control_mode: mode,
        source: 'frontend',
      }
      if (reason && reason.trim() !== '') {
        body.reason = reason.trim()
      }
      const response = await api.zones.setControlMode<unknown>(props.zoneId, body)

      applyControlModePayload(response)
      onControlModeChanged?.()
      showToast('Режим управления автоматикой обновлён.', 'success')
      return true
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to update automation control mode', { error, zoneId: props.zoneId, mode })
      showToast(extractHumanErrorMessage(error, 'Не удалось обновить режим управления.'), 'error')
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
      showToast(extractHumanErrorMessage(error, 'Не удалось выполнить manual-step.'), 'error')
    } finally {
      manualStepLoading.value[step] = false
    }
  }

  const diagnosticsLoading = ref(false)
  const solutionChangeLoading = ref(false)

  async function runDiagnostics(): Promise<boolean> {
    if (!props.zoneId || diagnosticsLoading.value) return false

    diagnosticsLoading.value = true
    try {
      await api.zones.startCycle(props.zoneId, { source: 'frontend' })
      showToast('Диагностика запущена.', 'success')
      await fetchAutomationControlMode()
      onControlModeChanged?.()
      return true
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to run diagnostics', { error, zoneId: props.zoneId })
      showToast(extractHumanErrorMessage(error, 'Не удалось запустить диагностику.'), 'error')
      return false
    } finally {
      diagnosticsLoading.value = false
    }
  }

  async function runSolutionChange(): Promise<boolean> {
    if (!props.zoneId || solutionChangeLoading.value) return false

    solutionChangeLoading.value = true
    try {
      await api.zones.startSolutionChange(props.zoneId, { source: 'frontend', trigger: 'operator' })
      showToast('Подмена раствора запущена — ожидается подтверждение оператора.', 'success')
      await fetchAutomationControlMode()
      onControlModeChanged?.()
      return true
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to start solution change', { error, zoneId: props.zoneId })
      showToast(extractHumanErrorMessage(error, 'Не удалось запустить подмену раствора.'), 'error')
      return false
    } finally {
      solutionChangeLoading.value = false
    }
  }

  async function refreshRuntimeState(): Promise<void> {
    if (!props.zoneId) return
    if (refreshInFlight) {
      refreshQueued = true
      return
    }

    const generation = refreshGeneration
    const requestedZoneId = props.zoneId
    refreshInFlight = true
    try {
      await fetchAutomationControlMode()
    } finally {
      // Ignore stale finally after zone switch — do not clear a newer refresh.
      if (generation !== refreshGeneration || props.zoneId !== requestedZoneId) {
        return
      }
      refreshInFlight = false
      if (refreshQueued) {
        refreshQueued = false
        void refreshRuntimeState()
      }
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

    // Команды MQTT не меняют control_mode — не дёргаем /control-mode на каждый status update.

    unsubscribeZoneEvents = subscribeManagedChannelEvents({
      channelName: `hydro.zones.${props.zoneId}`,
      componentTag: `zone-automation-runtime:events:${props.zoneId}`,
      eventHandlers: {
        '.EventCreated': (payload) => {
          const kind = String(payload.kind ?? '').trim().toUpperCase()
          if (
            kind === 'AUTOMATION_CONTROL_MODE_UPDATED'
            || kind.startsWith('MANUAL_STEP_')
          ) {
            void refreshRuntimeState()
          }
        },
        '.App\\Events\\EventCreated': (payload) => {
          const kind = String(payload.kind ?? '').trim().toUpperCase()
          if (
            kind === 'AUTOMATION_CONTROL_MODE_UPDATED'
            || kind.startsWith('MANUAL_STEP_')
          ) {
            void refreshRuntimeState()
          }
        },
      },
    })
  }

  function resetForZoneChange(): void {
    refreshGeneration += 1
    hydrateControlModeFromProp()
    if (!hasExplicitControlMode(props.zoneControlMode)) {
      automationControlMode.value = 'auto'
    }
    controlModeAvailable.value = ['auto', 'semi', 'manual']
    allowedManualSteps.value = []
    automationCurrentStage.value = null
    automationControlModeLoading.value = false
    automationControlModeSaving.value = false
    refreshInFlight = false
    refreshQueued = false
    diagnosticsLoading.value = false
    solutionChangeLoading.value = false
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

  watch(
    () => props.zoneControlMode,
    () => {
      hydrateControlModeFromProp()
    },
  )

  return {
    automationControlMode,
    controlModeAvailable,
    allowedManualSteps,
    automationCurrentStage,
    automationControlModeLoading,
    automationControlModeSaving,
    manualStepLoading,
    fetchAutomationControlMode,
    setAutomationControlMode,
    syncControlModeFromAutomationState,
    hydrateControlModeFromProp,
    runManualStep,
    runDiagnostics,
    runSolutionChange,
    diagnosticsLoading,
    solutionChangeLoading,
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
