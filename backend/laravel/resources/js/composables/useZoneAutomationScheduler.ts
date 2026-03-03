import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from '@/composables/useApi'
import type { AutomationLogicMode } from '@/composables/zoneAutomationUtils'
import {
  normalizeAutomationControlMode,
  normalizeAutomationManualSteps,
} from '@/composables/zoneAutomationUtils'
import { useWebSocket } from '@/composables/useWebSocket'
import type { AutomationControlMode, AutomationManualStep, AutomationState } from '@/types/Automation'
import type {
  ZoneAutomationTabProps,
  SchedulerTaskStatus,
  SchedulerTaskPreset,
} from '@/composables/zoneAutomationTypes'
import {
  schedulerTaskStatusVariant,
  schedulerTaskStatusLabel,
  schedulerTaskProcessStatusVariant,
  schedulerTaskProcessStatusLabel,
  schedulerTaskEventLabel,
  schedulerTaskTimelineStageLabel,
  schedulerTaskTimelineStepLabel,
  schedulerTaskTimelineItems,
  schedulerTaskDecisionLabel,
  schedulerTaskReasonLabel,
  schedulerTaskErrorLabel,
  schedulerTaskSlaMeta,
  schedulerTaskDoneMeta,
  formatSchedulerDateTime,
  taskMatchesPreset,
  taskMatchesSearch,
  type SchedulerTasksResponse,
  type SchedulerTaskResponse,
} from '@/composables/zoneSchedulerFormatters'

// ─── Composable ───────────────────────────────────────────────────────────────

export interface ZoneAutomationSchedulerDeps {
  get: <T = unknown>(url: string, config?: unknown) => Promise<{ data: T }>
  post: <T = unknown>(url: string, data?: unknown, config?: unknown) => Promise<{ data: T }>
  showToast: ToastHandler
}

export function useZoneAutomationScheduler(props: ZoneAutomationTabProps, deps: ZoneAutomationSchedulerDeps) {
  const { get, post, showToast } = deps
  const { subscribeToZoneCommands, subscribeToGlobalEvents, unsubscribeAll } = useWebSocket(
    showToast,
    'zone-automation-scheduler'
  )

  // ─── Refs ──────────────────────────────────────────────────────────────────
  const schedulerTaskIdInput = ref('')
  const schedulerTaskLookupLoading = ref(false)
  const schedulerTaskListLoading = ref(false)
  const schedulerTaskError = ref<string | null>(null)
  const schedulerTaskStatus = ref<SchedulerTaskStatus | null>(null)
  const recentSchedulerTasks = ref<SchedulerTaskStatus[]>([])
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
    irrigation_recovery_start: false,
    irrigation_recovery_stop: false,
  })
  const schedulerTaskSearch = ref('')
  const schedulerTaskPreset = ref<SchedulerTaskPreset>('all')
  const schedulerTasksUpdatedAt = ref<string | null>(null)
  let schedulerTasksPollTimer: ReturnType<typeof setTimeout> | null = null
  let schedulerTaskListRequestVersion = 0
  let schedulerTaskLookupRequestVersion = 0
  let schedulerRealtimeRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let schedulerRealtimeRefreshLastAt = 0
  let schedulerRealtimeRefreshInFlight = false
  let unsubscribeZoneCommands: (() => void) | null = null
  let unsubscribeGlobalEvents: (() => void) | null = null

  const REALTIME_REFRESH_MIN_INTERVAL_MS = 900

  const schedulerTaskPresetOptions: Array<{ value: SchedulerTaskPreset; label: string }> = [
    { value: 'all', label: 'Все' },
    { value: 'failed', label: 'Ошибки' },
    { value: 'deadline', label: 'Дедлайны' },
    { value: 'done_confirmed', label: 'DONE подтвержден' },
    { value: 'done_unconfirmed', label: 'DONE не подтвержден' },
  ]

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function normalizeTaskId(rawValue?: string): string {
    const source = typeof rawValue === 'string' ? rawValue : schedulerTaskIdInput.value
    return source.trim()
  }

  function normalizeReasonCode(raw: unknown): string {
    return String(raw ?? '').trim().toLowerCase()
  }

  function resolvePrimaryReasonCode(task: SchedulerTaskStatus | null): string {
    if (!task) return ''
    const direct = normalizeReasonCode(task.reason_code)
    if (direct) return direct
    const fromResult = normalizeReasonCode(task.result?.reason_code)
    if (fromResult) return fromResult
    const fromCurrentAction = normalizeReasonCode(task.process_state?.current_action?.reason_code)
    if (fromCurrentAction) return fromCurrentAction
    return ''
  }

  function syncControlModeFromAutomationState(snapshot: AutomationState | null): void {
    if (!snapshot || automationControlModeSaving.value) {
      return
    }
    automationControlMode.value = normalizeAutomationControlMode(snapshot.control_mode)
    allowedManualSteps.value = normalizeAutomationManualSteps(snapshot.allowed_manual_steps)
  }

  function extractApiErrorMessage(error: unknown, fallback: string): string {
    const err = error as { response?: { data?: unknown } }
    const data = err?.response?.data
    if (typeof data === 'string' && data.trim() !== '') {
      return data.trim()
    }
    if (data && typeof data === 'object') {
      const payload = data as Record<string, unknown>
      const message = payload.message
      if (typeof message === 'string' && message.trim() !== '') {
        return message.trim()
      }
      const payloadError = payload.error
      if (typeof payloadError === 'string' && payloadError.trim() !== '') {
        return payloadError.trim()
      }
      const code = payload.code
      if (typeof code === 'string' && code.trim() !== '') {
        return code.trim()
      }
      const detail = payload.detail
      if (typeof detail === 'string' && detail.trim() !== '') {
        return detail.trim()
      }
      if (detail && typeof detail === 'object') {
        const detailPayload = detail as Record<string, unknown>
        const detailMessage = detailPayload.message
        if (typeof detailMessage === 'string' && detailMessage.trim() !== '') {
          return detailMessage.trim()
        }
        const detailError = detailPayload.error
        if (typeof detailError === 'string' && detailError.trim() !== '') {
          return detailError.trim()
        }
        const detailCode = detailPayload.code
        if (typeof detailCode === 'string' && detailCode.trim() !== '') {
          return detailCode.trim()
        }
      }
    }
    return fallback
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const filteredRecentSchedulerTasks = computed(() => {
    return recentSchedulerTasks.value.filter((task) => {
      return taskMatchesPreset(task, schedulerTaskPreset.value) && taskMatchesSearch(task, schedulerTaskSearch.value)
    })
  })

  // ─── Polling ───────────────────────────────────────────────────────────────

  async function fetchRecentSchedulerTasks(): Promise<void> {
    if (!props.zoneId) {
      recentSchedulerTasks.value = []
      schedulerTasksUpdatedAt.value = null
      schedulerTaskListLoading.value = false
      return
    }

    const requestZoneId = props.zoneId
    const requestVersion = ++schedulerTaskListRequestVersion
    schedulerTaskListLoading.value = true
    schedulerTaskError.value = null
    try {
      const response = await get<SchedulerTasksResponse>(`/api/zones/${requestZoneId}/scheduler-tasks`, {
        params: { limit: 20 },
      })

      if (requestVersion !== schedulerTaskListRequestVersion || requestZoneId !== props.zoneId) {
        return
      }

      const payload = response.data as SchedulerTasksResponse
      const items = Array.isArray(payload?.data) ? payload.data : []
      recentSchedulerTasks.value = items
      schedulerTasksUpdatedAt.value = new Date().toISOString()
    } catch (error) {
      if (requestVersion !== schedulerTaskListRequestVersion || requestZoneId !== props.zoneId) {
        return
      }
      logger.warn('[ZoneAutomationTab] Failed to fetch scheduler tasks', { error, zoneId: props.zoneId })
      schedulerTaskError.value = 'Не удалось получить список scheduler-задач.'
    } finally {
      if (requestVersion === schedulerTaskListRequestVersion && requestZoneId === props.zoneId) {
        schedulerTaskListLoading.value = false
      }
    }
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
      const response = await get<{ data?: { control_mode?: string; allowed_manual_steps?: unknown[] } }>(
        `/api/zones/${requestedZoneId}/control-mode`
      )
      if (props.zoneId !== requestedZoneId) return
      const payload = response.data?.data ?? {}
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
    schedulerTaskError.value = null
    try {
      const response = await post<{ data?: { control_mode?: string; allowed_manual_steps?: unknown[] } }>(
        `/api/zones/${props.zoneId}/control-mode`,
        {
          control_mode: mode,
          source: 'frontend',
        }
      )
      const payload = response.data?.data ?? {}
      automationControlMode.value = normalizeAutomationControlMode(payload.control_mode ?? mode)
      allowedManualSteps.value = normalizeAutomationManualSteps(payload.allowed_manual_steps)
      showToast('Режим управления автоматикой обновлён.', 'success')
      return true
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to update automation control mode', { error, zoneId: props.zoneId, mode })
      schedulerTaskError.value = extractApiErrorMessage(error, 'Не удалось обновить режим управления.')
      return false
    } finally {
      automationControlModeSaving.value = false
    }
  }

  async function runManualStep(step: AutomationManualStep): Promise<void> {
    if (!props.zoneId) return
    manualStepLoading.value[step] = true
    schedulerTaskError.value = null
    try {
      const response = await post<{ data?: { task_id?: string | null } }>(
        `/api/zones/${props.zoneId}/manual-step`,
        {
          manual_step: step,
          source: 'frontend_manual_step',
        }
      )
      showToast('Команда manual-step отправлена.', 'success')
      const taskId = String(response.data?.data?.task_id ?? '').trim()
      await fetchRecentSchedulerTasks()
      if (taskId) {
        await lookupSchedulerTask(taskId)
      }
    } catch (error: unknown) {
      logger.warn('[ZoneAutomationTab] Failed to run manual step', { error, zoneId: props.zoneId, step })
      schedulerTaskError.value = extractApiErrorMessage(error, 'Не удалось выполнить manual-step.')
    } finally {
      manualStepLoading.value[step] = false
    }
  }

  async function lookupSchedulerTask(taskIdRaw?: string): Promise<void> {
    if (!props.zoneId) return

    const taskId = normalizeTaskId(taskIdRaw)
    if (!taskId) {
      schedulerTaskStatus.value = null
      schedulerTaskError.value = 'Укажите task_id вида st-... или intent-...'
      return
    }

    const requestZoneId = props.zoneId
    const requestVersion = ++schedulerTaskLookupRequestVersion
    schedulerTaskLookupLoading.value = true
    schedulerTaskError.value = null
    try {
      const response = await get<SchedulerTaskResponse>(
        `/api/zones/${requestZoneId}/scheduler-tasks/${encodeURIComponent(taskId)}`
      )

      if (requestVersion !== schedulerTaskLookupRequestVersion || requestZoneId !== props.zoneId) {
        return
      }

      schedulerTaskStatus.value = (response.data as SchedulerTaskResponse)?.data ?? null
      schedulerTaskIdInput.value = taskId
    } catch (error: unknown) {
      if (requestVersion !== schedulerTaskLookupRequestVersion || requestZoneId !== props.zoneId) {
        return
      }
      logger.warn('[ZoneAutomationTab] Failed to lookup scheduler task', { error, zoneId: props.zoneId, taskId })
      schedulerTaskStatus.value = null
      schedulerTaskError.value = extractApiErrorMessage(error, 'Не удалось получить статус задачи.')
    } finally {
      if (requestVersion === schedulerTaskLookupRequestVersion && requestZoneId === props.zoneId) {
        schedulerTaskLookupLoading.value = false
        scheduleSchedulerTasksPoll()
      }
    }
  }

  function clearSchedulerTasksPollTimer(): void {
    if (schedulerTasksPollTimer) {
      clearTimeout(schedulerTasksPollTimer)
      schedulerTasksPollTimer = null
    }
  }

  function clearRealtimeRefreshTimer(): void {
    if (schedulerRealtimeRefreshTimer) {
      clearTimeout(schedulerRealtimeRefreshTimer)
      schedulerRealtimeRefreshTimer = null
    }
  }

  async function refreshSchedulerFromRealtime(reason: string): Promise<void> {
    if (!props.zoneId) return
    if (schedulerRealtimeRefreshInFlight) return

    schedulerRealtimeRefreshInFlight = true
    try {
      await fetchRecentSchedulerTasks()

      const activeTaskId = normalizeTaskId(schedulerTaskStatus.value?.task_id)
      if (activeTaskId) {
        await lookupSchedulerTask(activeTaskId)
      }

      if (reason === 'control_mode_event') {
        await fetchAutomationControlMode()
      }
    } finally {
      schedulerRealtimeRefreshInFlight = false
    }
  }

  function scheduleRealtimeRefresh(reason: string): void {
    if (!props.zoneId) return

    const now = Date.now()
    const elapsed = now - schedulerRealtimeRefreshLastAt
    if (elapsed >= REALTIME_REFRESH_MIN_INTERVAL_MS) {
      schedulerRealtimeRefreshLastAt = now
      void refreshSchedulerFromRealtime(reason)
      return
    }

    if (schedulerRealtimeRefreshTimer) {
      return
    }

    schedulerRealtimeRefreshTimer = setTimeout(() => {
      schedulerRealtimeRefreshTimer = null
      schedulerRealtimeRefreshLastAt = Date.now()
      void refreshSchedulerFromRealtime(reason)
    }, REALTIME_REFRESH_MIN_INTERVAL_MS - elapsed)
  }

  function shouldRefreshByGlobalKind(kind: string): boolean {
    if (kind === 'AUTOMATION_CONTROL_MODE_UPDATED') return true
    return (
      kind.startsWith('SCHEDULE_TASK_')
      || kind.startsWith('TASK_')
      || kind.startsWith('COMMAND_')
      || kind.startsWith('MANUAL_STEP_')
    )
  }

  function stopRealtimeSubscriptions(): void {
    clearRealtimeRefreshTimer()
    if (unsubscribeZoneCommands) {
      unsubscribeZoneCommands()
      unsubscribeZoneCommands = null
    }
    if (unsubscribeGlobalEvents) {
      unsubscribeGlobalEvents()
      unsubscribeGlobalEvents = null
    }
  }

  function startRealtimeSubscriptions(): void {
    stopRealtimeSubscriptions()
    if (!props.zoneId) return
    if (import.meta.env.MODE === 'test') return

    unsubscribeZoneCommands = subscribeToZoneCommands(props.zoneId, (event) => {
      const eventZoneId = typeof event.zoneId === 'number' ? event.zoneId : null
      if (eventZoneId !== null && eventZoneId !== props.zoneId) {
        return
      }
      scheduleRealtimeRefresh('command_event')
    })

    unsubscribeGlobalEvents = subscribeToGlobalEvents((event) => {
      if (!props.zoneId) return
      const eventZoneId = typeof event.zoneId === 'number' ? event.zoneId : null
      if (eventZoneId === null || eventZoneId !== props.zoneId) {
        return
      }

      const kind = String(event.kind ?? '').trim().toUpperCase()
      if (!shouldRefreshByGlobalKind(kind)) {
        return
      }

      if (kind === 'AUTOMATION_CONTROL_MODE_UPDATED') {
        scheduleRealtimeRefresh('control_mode_event')
        return
      }

      scheduleRealtimeRefresh('global_event')
    })
  }

  function hasActiveSchedulerTask(): boolean {
    const isActive = (status: string | null | undefined): boolean => {
      const s = String(status ?? '').trim().toLowerCase()
      return s === 'accepted' || s === 'running'
    }
    if (isActive(schedulerTaskStatus.value?.status)) return true
    return recentSchedulerTasks.value.some((task) => isActive(task.status))
  }

  function getSchedulerPollDelayMs(): number {
    return hasActiveSchedulerTask() ? 3000 : 15000
  }

  function scheduleSchedulerTasksPoll(): void {
    if (import.meta.env.MODE === 'test') return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return

    clearSchedulerTasksPollTimer()
    schedulerTasksPollTimer = setTimeout(() => {
      void pollSchedulerTasksCycle()
    }, getSchedulerPollDelayMs())
  }

  async function pollSchedulerTasksCycle(): Promise<void> {
    await fetchRecentSchedulerTasks()
    scheduleSchedulerTasksPoll()
  }

  function handleVisibilityChange(): void {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') {
      void pollSchedulerTasksCycle()
      return
    }
    clearSchedulerTasksPollTimer()
  }

  // ─── Zone change reset ─────────────────────────────────────────────────────

  function resetForZoneChange(): void {
    schedulerTaskListRequestVersion += 1
    schedulerTaskLookupRequestVersion += 1
    schedulerTaskIdInput.value = ''
    schedulerTaskStatus.value = null
    recentSchedulerTasks.value = []
    schedulerTaskError.value = null
    schedulerTasksUpdatedAt.value = null
    schedulerTaskListLoading.value = false
    schedulerTaskLookupLoading.value = false
    automationControlMode.value = 'auto'
    allowedManualSteps.value = []
    automationControlModeLoading.value = false
    automationControlModeSaving.value = false
    // Сбрасываем флаг in-flight: иначе WS-рефреш новой зоны будет заблокирован
    // до завершения запроса старой зоны (schedulerRealtimeRefreshInFlight остался true)
    schedulerRealtimeRefreshInFlight = false
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
    // State
    schedulerTaskIdInput,
    schedulerTaskLookupLoading,
    schedulerTaskListLoading,
    schedulerTaskError,
    schedulerTaskStatus,
    automationControlMode,
    allowedManualSteps,
    automationControlModeLoading,
    automationControlModeSaving,
    manualStepLoading,
    recentSchedulerTasks,
    filteredRecentSchedulerTasks,
    schedulerTaskSearch,
    schedulerTaskPreset,
    schedulerTaskPresetOptions,
    schedulerTasksUpdatedAt,
    // Actions
    fetchRecentSchedulerTasks,
    fetchAutomationControlMode,
    lookupSchedulerTask,
    setAutomationControlMode,
    syncControlModeFromAutomationState,
    runManualStep,
    clearSchedulerTasksPollTimer,
    hasActiveSchedulerTask,
    scheduleSchedulerTasksPoll,
    pollSchedulerTasksCycle,
    handleVisibilityChange,
    resetForZoneChange,
    // Formatters (delegated to zoneSchedulerFormatters)
    schedulerTaskStatusVariant,
    schedulerTaskStatusLabel,
    schedulerTaskProcessStatusVariant,
    schedulerTaskProcessStatusLabel,
    schedulerTaskEventLabel,
    schedulerTaskTimelineStageLabel,
    schedulerTaskTimelineStepLabel,
    schedulerTaskTimelineItems,
    schedulerTaskDecisionLabel,
    schedulerTaskReasonLabel,
    schedulerTaskErrorLabel,
    schedulerTaskSlaMeta,
    schedulerTaskDoneMeta,
    formatDateTime: formatSchedulerDateTime,
  }
}

// Re-export AutomationLogicMode for consumers
export type { AutomationLogicMode }
