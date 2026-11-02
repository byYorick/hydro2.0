import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import { api } from '@/services/api'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { AutomationState } from '@/types/Automation'
import type {
  ExecutionFailureSummary,
  ExecutionResponse,
  ExecutionRun,
  PlanLane,
  PlanWindow,
  SchedulerDiagnostics,
  SchedulerDiagnosticsResponse,
  ScheduleWorkspace,
  ScheduleWorkspaceResponse,
} from '@/composables/zoneScheduleWorkspaceTypes'
import { asNonEmptyString, formatDateTime, formatRelativeTrigger, statusVariant, controlModeLabel, laneLabel, decisionLabel, statusLabel, workflowStageLabel } from '@/utils/schedulerLabels'

export function useZoneScheduleWorkspace(props: ZoneAutomationTabProps) {
  const horizon = ref<'24h' | '7d'>('24h')
  const workspace = ref<ScheduleWorkspace | null>(null)
  const automationState = ref<AutomationState | null>(null)
  const selectedExecution = ref<ExecutionRun | null>(null)
  const selectedExecutionId = ref<string | null>(null)
  const detailError = ref<string | null>(null)
  const diagnostics = ref<SchedulerDiagnostics | null>(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const diagnosticsLoading = ref(false)
  const error = ref<string | null>(null)
  const diagnosticsError = ref<string | null>(null)
  const updatedAt = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let unsubscribeControlModeEvents: (() => void) | null = null
  let workspaceRequestSeq = 0
  const requests = { state: 0, execution: 0, diagnostics: 0 }
  let disposed = false

  /**
   * `apiGet` уже снимает status-envelope `{status, data: ...}` через `extractData`,
   * поэтому в норме сюда приходит уже inner-payload. Но если бэкенд (или тест-mock)
   * вдруг вернул wrapped-форму — корректно вытащим вложенный `.data`.
   */
  function unwrapEnvelope<T>(response: T | { data?: T } | null | undefined): T | null {
    if (response === null || response === undefined) return null
    if (
      typeof response === 'object'
      && response !== null
      && 'data' in (response as Record<string, unknown>)
      && (response as { data?: T }).data !== undefined
      && (response as { data?: T }).data !== null
    ) {
      return (response as { data: T }).data
    }
    return response as T
  }

  const lanes = computed<PlanLane[]>(() => workspace.value?.plan?.lanes ?? [])
  const windows = computed<PlanWindow[]>(() => workspace.value?.plan?.windows ?? [])
  const recentRuns = computed<ExecutionRun[]>(() => workspace.value?.execution?.recent_runs ?? [])
  const activeRun = computed<ExecutionRun | null>(() => workspace.value?.execution?.active_run ?? null)
  const latestFailure = computed<ExecutionFailureSummary | null>(() => workspace.value?.execution?.latest_failure ?? null)
  const executionCounters = computed(() => workspace.value?.execution?.counters ?? {
    active: 0,
    completed_24h: 0,
    failed_24h: 0,
  })
  const executableTaskTypes = computed<string[]>(() => workspace.value?.capabilities?.executable_task_types ?? [])
  const executableWindows = computed<PlanWindow[]>(() => {
    const executable = new Set(executableTaskTypes.value)

    return windows.value
      .filter((window) => executable.has(String(window.task_type ?? '').trim()))
      .sort((a, b) => Date.parse(a.trigger_at) - Date.parse(b.trigger_at))
  })
  const nextExecutableWindows = computed(() => executableWindows.value.slice(0, 3))
  const configOnlyLanes = computed<PlanLane[]>(() => lanes.value.filter((lane) => !lane.executable))
  const manualSchedules = computed(() => workspace.value?.manual_schedules ?? [])
  type AttentionEntry = { tone: 'danger' | 'warning' | 'info', title: string, detail: string | null }

  const attentionAlerts = computed((): AttentionEntry[] => {
    const items: AttentionEntry[] = []

    if (latestFailure.value) {
      const failureMessage = resolveHumanErrorMessage({
        code: latestFailure.value.error_code,
        message: latestFailure.value.error_message,
        humanMessage: latestFailure.value.human_error_message,
      }, 'Неизвестная ошибка') || 'Неизвестная ошибка'
      const failureDetail = latestFailure.value.at
        ? `Зафиксировано ${formatDateTime(latestFailure.value.at)}`
        : null
      items.push({
        tone: 'danger',
        title: `Последняя ошибка: ${laneLabel(latestFailure.value.task_type)} · ${failureMessage}`,
        detail: failureDetail,
      })
    }

    const runtime = String(workspace.value?.control?.automation_runtime ?? '').trim().toLowerCase()
    if (runtime === 'ae3') {
      const caps = workspace.value?.capabilities
      const nonExecRaw = caps?.non_executable_planned_task_types
      const hasTypedList = Array.isArray(nonExecRaw)
      const nonExec = hasTypedList ? nonExecRaw : []
      const showLimit = (hasTypedList && nonExec.length > 0) || (!hasTypedList && configOnlyLanes.value.length > 0)

      if (showLimit) {
        const typesHint = nonExec.length > 0 ? nonExec.join(', ') : null
        const autoHint = executableTaskTypes.value.length > 0
          ? `Сейчас автодиспатч scheduler покрывает: ${executableTaskTypes.value.join(', ')}.`
          : ''
        items.push({
          tone: 'warning',
          title: 'Не все типы расписания запускаются автоматически (AE3)',
          detail: typesHint
            ? `${autoHint ? `${autoHint} ` : ''}Не диспатчатся из scheduler: ${typesHint}. Окна в графике отражают конфигурацию effective targets.`.trim()
            : `${autoHint ? `${autoHint} ` : ''}Часть дорожек в графике относится к подсистемам без автоматического dispatch из этого планировщика (см. подписи дорожек).`.trim(),
        })
      }
    }

    if (executionCounters.value.failed_24h > 0) {
      const latestFailureCode = asNonEmptyString(latestFailure.value?.error_code)
      items.push({
        tone: latestFailure.value ? 'warning' : 'danger',
        title: `Ошибок за 24ч: ${executionCounters.value.failed_24h}`,
        detail: latestFailureCode === 'start_cycle_zone_busy'
          ? 'Повторные старты полива отклоняются, пока зона занята активным intent.'
          : 'Есть неуспешные scheduler/AE исполнения, которые требуют внимания.',
      })
    }

    if (activeRun.value && automationState.value?.state_label) {
      const st = automationState.value.state_details
      const failed = Boolean(st?.failed)
      if (failed) {
        const headline = asNonEmptyString(st?.human_error_message)
          ?? asNonEmptyString(st?.error_message)
          ?? automationState.value.state_label
        items.push({
          tone: 'danger',
          title: `Сбой автоматики: ${headline}`,
          detail: activeRun.value.current_stage || automationState.value.current_stage || null,
        })
      }
    }

    return items.slice(0, 4)
  })

  const attentionStatus = computed((): AttentionEntry[] => {
    if (!activeRun.value || !automationState.value?.state_label) {
      return []
    }
    const st = automationState.value.state_details
    const failed = Boolean(st?.failed)
    if (failed) {
      return []
    }
    return [
      {
        tone: 'info',
        title: `Сейчас выполняется: ${automationState.value.state_label}`,
        detail: activeRun.value.current_stage || automationState.value.current_stage || null,
      },
    ]
  })
  async function fetchWorkspace(): Promise<void> {
    if (!props.zoneId) {
      workspace.value = null
      selectedExecution.value = null
      updatedAt.value = null
      loading.value = false
      return
    }

    const requestSeq = ++workspaceRequestSeq
    const requestedZoneId = props.zoneId
    loading.value = true
    error.value = null

    try {
      const response = await api.zones.scheduleWorkspace<ScheduleWorkspace | ScheduleWorkspaceResponse>(
        requestedZoneId,
        { horizon: horizon.value },
      )
      if (disposed || requestSeq !== workspaceRequestSeq || props.zoneId !== requestedZoneId) {
        return
      }
      workspace.value = unwrapEnvelope<ScheduleWorkspace>(response)
      updatedAt.value = new Date().toISOString()

      const nextSelectedExecutionId = selectedExecutionId.value
      if (nextSelectedExecutionId) {
        if (!detailLoading.value) await fetchExecution(nextSelectedExecutionId, { silent: true })
      }
    } catch (fetchError) {
      if (disposed || requestSeq !== workspaceRequestSeq || props.zoneId !== requestedZoneId) {
        return
      }
      logger.warn('[ZoneSchedulerTab] Failed to fetch schedule workspace', { fetchError, zoneId: requestedZoneId })
      error.value = 'Не удалось получить workspace планировщика.'
    } finally {
      if (requestSeq === workspaceRequestSeq && props.zoneId === requestedZoneId) {
        loading.value = false
      }
    }
  }

  function clearSelectedExecution(): void {
    requests.execution += 1
    selectedExecutionId.value = null
    detailLoading.value = false
    detailError.value = null
    selectedExecution.value = null
  }

  function selectExecution(executionId: string): void {
    void fetchExecution(executionId)
  }

  async function fetchAutomationState(options?: { silent?: boolean }): Promise<void> {
    const zoneId = props.zoneId
    const request = ++requests.state
    if (!zoneId) {
      automationState.value = null
      return
    }

    try {
      const response = await api.zones.getState<AutomationState | { data?: AutomationState }>(zoneId)
      if (disposed || zoneId !== props.zoneId || request !== requests.state) return
      automationState.value = unwrapEnvelope<AutomationState>(response)
    } catch (fetchError) {
      if (disposed || zoneId !== props.zoneId || request !== requests.state) return
      logger.warn('[ZoneSchedulerTab] Failed to fetch automation state', { fetchError, zoneId: props.zoneId })
      if (!options?.silent && !error.value) {
        error.value = 'Не удалось получить состояние зоны.'
      }
    }
  }

  async function fetchExecution(executionId: string, options?: { silent?: boolean }): Promise<void> {
    const normalizedExecutionId = String(executionId ?? '').trim()
    if (!props.zoneId || normalizedExecutionId === '') {
      return
    }
    const zoneId = props.zoneId
    const request = ++requests.execution
    selectedExecutionId.value = normalizedExecutionId

    if (!options?.silent) {
      detailLoading.value = true
      detailError.value = null
      selectedExecution.value = null
    }

    try {
      const response = await api.zones.getExecution<ExecutionRun | ExecutionResponse>(zoneId, normalizedExecutionId)
      if (disposed || zoneId !== props.zoneId || request !== requests.execution) return
      selectedExecution.value = unwrapEnvelope<ExecutionRun>(response)
      detailError.value = null
    } catch (fetchError) {
      if (disposed || zoneId !== props.zoneId || request !== requests.execution) return
      logger.warn('[ZoneSchedulerTab] Failed to fetch execution detail', { fetchError, zoneId: props.zoneId, executionId: normalizedExecutionId })
      if (!options?.silent) {
        detailError.value = 'Не удалось получить детали выполнения.'
      }
    } finally {
      if (!disposed && request === requests.execution) {
        detailLoading.value = false
      }
    }
  }

  async function fetchDiagnostics(options?: { silent?: boolean }): Promise<void> {
    const zoneId = props.zoneId
    const request = ++requests.diagnostics
    if (!zoneId) {
      diagnostics.value = null
      diagnosticsError.value = null
      diagnosticsLoading.value = false
      return
    }

    if (!options?.silent) {
      diagnosticsLoading.value = true
    }

    diagnosticsError.value = null

    try {
      const response = await api.zones.schedulerDiagnostics<SchedulerDiagnostics | SchedulerDiagnosticsResponse>(zoneId)
      if (disposed || zoneId !== props.zoneId || request !== requests.diagnostics) return
      diagnostics.value = unwrapEnvelope<SchedulerDiagnostics>(response)
    } catch (fetchError) {
      if (disposed || zoneId !== props.zoneId || request !== requests.diagnostics) return
      logger.warn('[ZoneSchedulerTab] Failed to fetch scheduler diagnostics', { fetchError, zoneId: props.zoneId })
      diagnostics.value = null
      diagnosticsError.value = 'Не удалось получить инженерную диагностику.'
    } finally {
      if (request === requests.diagnostics) {
        diagnosticsLoading.value = false
      }
    }
  }

  function setHorizon(nextHorizon: '24h' | '7d'): void {
    horizon.value = nextHorizon
  }

  function clearDiagnostics(): void {
    requests.diagnostics += 1
    diagnostics.value = null
    diagnosticsError.value = null
    diagnosticsLoading.value = false
  }

  function clearPollTimer(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function schedulePoll(): void {
    clearPollTimer()
    if (disposed || import.meta.env.MODE === 'test' || document.visibilityState === 'hidden') return
    const delay = activeRun.value ? 3000 : 15000
    pollTimer = window.setTimeout(() => {
      void pollCycle()
    }, delay)
  }

  async function pollCycle(): Promise<void> {
    if (disposed || document.visibilityState === 'hidden') return
    await refreshWorkspace()
  }

  async function refreshWorkspace(): Promise<void> {
    const zoneId = props.zoneId
    await Promise.all([
      fetchWorkspace(),
      fetchAutomationState({ silent: true }),
    ])
    if (!disposed && props.zoneId === zoneId) schedulePoll()
  }

  function handleVisibilityChange(): void {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') {
      void pollCycle()
      return
    }
    clearPollTimer()
  }

  function stopControlModeEventSubscription(): void {
    if (unsubscribeControlModeEvents) {
      unsubscribeControlModeEvents()
      unsubscribeControlModeEvents = null
    }
  }

  function startControlModeEventSubscription(): void {
    stopControlModeEventSubscription()
    const zoneId = props.zoneId
    if (zoneId === null || zoneId === undefined || import.meta.env.MODE === 'test') {
      return
    }

    const refreshOnControlModeEvent = (payload: { kind?: unknown }): void => {
      const kind = String(payload.kind ?? '').trim().toUpperCase()
      if (kind === 'AUTOMATION_CONTROL_MODE_UPDATED') {
        void fetchWorkspace()
      }
    }

    unsubscribeControlModeEvents = subscribeManagedChannelEvents({
      channelName: `hydro.zones.${zoneId}`,
      componentTag: `zone-scheduler-workspace:events:${zoneId}`,
      eventHandlers: {
        '.EventCreated': refreshOnControlModeEvent,
        '.App\\Events\\EventCreated': refreshOnControlModeEvent,
      },
    })
  }

  onMounted(() => {
    startControlModeEventSubscription()
    void refreshWorkspace()
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })

  onUnmounted(() => {
    disposed = true
    workspaceRequestSeq += 1
    clearPollTimer()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    stopControlModeEventSubscription()
  })

  watch(
    () => props.zoneId,
    () => {
      workspaceRequestSeq += 1
      requests.state += 1
      requests.execution += 1
      selectedExecutionId.value = null
      detailLoading.value = false
      updatedAt.value = null
      clearDiagnostics()
      workspace.value = null
      selectedExecution.value = null
      detailError.value = null
      automationState.value = null
      error.value = null
      startControlModeEventSubscription()
      void refreshWorkspace()
    },
  )

  return {
    horizon,
    workspace,
    automationState,
    selectedExecution,
    selectedExecutionId,
    detailError,
    diagnostics,
    loading,
    detailLoading,
    diagnosticsLoading,
    error,
    diagnosticsError,
    updatedAt,
    lanes,
    windows,
    recentRuns,
    activeRun,
    latestFailure,
    executionCounters,
    nextExecutableWindows,
    executableWindows,
    configOnlyLanes,
    manualSchedules,
    attentionAlerts,
    attentionStatus,
    fetchWorkspace,
    refreshWorkspace,
    fetchAutomationState,
    fetchExecution,
    fetchDiagnostics,
    selectExecution,
    clearSelectedExecution,
    setHorizon,
    clearDiagnostics,
    clearPollTimer,
    schedulePoll,
    pollCycle,
    handleVisibilityChange,
    formatDateTime,
    formatRelativeTrigger,
    statusVariant,
    statusLabel,
    controlModeLabel,
    laneLabel,
    workflowStageLabel,
    decisionLabel,
  }
}
