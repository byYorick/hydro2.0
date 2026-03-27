import { computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import type { ToastHandler } from '@/composables/useApi'
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

export interface ZoneScheduleWorkspaceDeps {
  get: <T = unknown>(url: string, config?: unknown) => Promise<{ data: T }>
  showToast: ToastHandler
}

export interface TimelineDisplayItem {
  key: string
  event_type: string
  at: string | null
  label: string
  detail: string | null
  grouped?: boolean
}

export function useZoneScheduleWorkspace(props: ZoneAutomationTabProps, deps: ZoneScheduleWorkspaceDeps) {
  const { get } = deps

  const horizon = ref<'24h' | '7d'>('24h')
  const workspace = ref<ScheduleWorkspace | null>(null)
  const automationState = ref<AutomationState | null>(null)
  const selectedExecution = ref<ExecutionRun | null>(null)
  const diagnostics = ref<SchedulerDiagnostics | null>(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const diagnosticsLoading = ref(false)
  const error = ref<string | null>(null)
  const diagnosticsError = ref<string | null>(null)
  const updatedAt = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setTimeout> | null = null

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
  const nextExecutableWindows = computed<PlanWindow[]>(() => {
    const executable = new Set(executableTaskTypes.value)

    return windows.value
      .filter((window) => executable.has(String(window.task_type ?? '').trim()))
      .slice(0, 3)
  })
  const configOnlyLanes = computed<PlanLane[]>(() => lanes.value.filter((lane) => !lane.executable))
  const activeProcessLabels = computed<string[]>(() => {
    const current = automationState.value?.active_processes
    if (!current) return []

    const labels: string[] = []
    if (current.pump_in) labels.push('Насос набора')
    if (current.circulation_pump) labels.push('Рециркуляционный насос')
    if (current.ph_correction) labels.push('Коррекция pH')
    if (current.ec_correction) labels.push('Коррекция EC')

    return labels
  })
  const attentionItems = computed(() => {
    const items: Array<{ tone: 'danger' | 'warning' | 'info', title: string, detail: string | null }> = []

    if (latestFailure.value) {
      const failureCode = latestFailure.value.error_code || latestFailure.value.error_message || 'Неизвестная ошибка'
      const failureDetail = latestFailure.value.error_message && latestFailure.value.error_message !== failureCode
        ? latestFailure.value.error_message
        : latestFailure.value.at
          ? `Зафиксировано ${formatDateTime(latestFailure.value.at)}`
          : null
      items.push({
        tone: 'danger',
        title: `Последняя ошибка: ${laneLabel(latestFailure.value.task_type)} · ${failureCode}`,
        detail: failureDetail,
      })
    }

    if (executionCounters.value.failed_24h > 0) {
      items.push({
        tone: latestFailure.value ? 'warning' : 'danger',
        title: `Ошибок за 24ч: ${executionCounters.value.failed_24h}`,
        detail: latestFailure.value?.error_code === 'start_cycle_zone_busy'
          ? 'Повторные старты полива отклоняются, пока зона занята активным intent.'
          : 'Есть неуспешные scheduler/AE исполнения, которые требуют внимания.',
      })
    }

    if (activeRun.value && automationState.value?.state_label) {
      items.push({
        tone: 'info',
        title: `Сейчас выполняется: ${automationState.value.state_label}`,
        detail: activeRun.value.current_stage || automationState.value.current_stage || null,
      })
    }

    return items.slice(0, 3)
  })
  const condensedTimeline = computed<TimelineDisplayItem[]>(() => collapseTimeline(selectedExecution.value?.timeline ?? []))

  const laneWindows = computed<Record<string, PlanWindow[]>>(() => {
    const grouped: Record<string, PlanWindow[]> = {}
    for (const window of windows.value) {
      const key = String(window.task_type ?? '').trim()
      if (key === '') continue
      if (!grouped[key]) {
        grouped[key] = []
      }
      grouped[key].push(window)
    }
    return grouped
  })

  async function fetchWorkspace(): Promise<void> {
    if (!props.zoneId) {
      workspace.value = null
      selectedExecution.value = null
      updatedAt.value = null
      loading.value = false
      return
    }

    loading.value = true
    error.value = null

    try {
      const response = await get<ScheduleWorkspaceResponse>(`/api/zones/${props.zoneId}/schedule-workspace`, {
        params: { horizon: horizon.value },
      })
      workspace.value = response.data?.data ?? null
      updatedAt.value = new Date().toISOString()

      const nextSelectedExecutionId = selectedExecution.value?.execution_id?.trim()
      if (nextSelectedExecutionId) {
        await fetchExecution(nextSelectedExecutionId, { silent: true })
      } else if (activeRun.value?.execution_id) {
        await fetchExecution(activeRun.value.execution_id, { silent: true })
      } else if (recentRuns.value[0]?.execution_id) {
        await fetchExecution(recentRuns.value[0].execution_id, { silent: true })
      } else {
        selectedExecution.value = null
      }
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch schedule workspace', { fetchError, zoneId: props.zoneId })
      error.value = 'Не удалось получить workspace планировщика.'
    } finally {
      loading.value = false
    }
  }

  async function fetchAutomationState(options?: { silent?: boolean }): Promise<void> {
    if (!props.zoneId) {
      automationState.value = null
      return
    }

    try {
      const response = await get<AutomationState | { data?: AutomationState }>(`/api/zones/${props.zoneId}/state`)
      const payload = isRecord(response.data) && isRecord(response.data.data)
        ? response.data.data as AutomationState
        : response.data as AutomationState
      automationState.value = payload
    } catch (fetchError) {
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

    if (!options?.silent) {
      detailLoading.value = true
    }

    try {
      const response = await get<ExecutionResponse>(`/api/zones/${props.zoneId}/executions/${encodeURIComponent(normalizedExecutionId)}`)
      selectedExecution.value = response.data?.data ?? null
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch execution detail', { fetchError, zoneId: props.zoneId, executionId: normalizedExecutionId })
      if (!options?.silent) {
        error.value = 'Не удалось получить детали выполнения.'
      }
    } finally {
      if (!options?.silent) {
        detailLoading.value = false
      }
    }
  }

  async function fetchDiagnostics(options?: { silent?: boolean }): Promise<void> {
    if (!props.zoneId) {
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
      const response = await get<SchedulerDiagnosticsResponse>(`/api/zones/${props.zoneId}/scheduler-diagnostics`)
      diagnostics.value = response.data?.data ?? null
    } catch (fetchError) {
      logger.warn('[ZoneSchedulerTab] Failed to fetch scheduler diagnostics', { fetchError, zoneId: props.zoneId })
      diagnostics.value = null
      diagnosticsError.value = 'Не удалось получить инженерную диагностику.'
    } finally {
      if (!options?.silent) {
        diagnosticsLoading.value = false
      }
    }
  }

  function setHorizon(nextHorizon: '24h' | '7d'): void {
    horizon.value = nextHorizon
  }

  function clearDiagnostics(): void {
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
    const delay = activeRun.value ? 3000 : 15000
    pollTimer = window.setTimeout(() => {
      void pollCycle()
    }, delay)
  }

  async function pollCycle(): Promise<void> {
    await Promise.all([
      fetchWorkspace(),
      fetchAutomationState({ silent: true }),
    ])
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      return
    }
    schedulePoll()
  }

  function handleVisibilityChange(): void {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') {
      void pollCycle()
      return
    }
    clearPollTimer()
  }

  function formatDateTime(value: string | null | undefined): string {
    if (!value) return '—'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '—'

    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(parsed)
  }

  function formatRelativeTrigger(value: string | null | undefined): string {
    if (!value) return '—'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '—'
    const diffMinutes = Math.round((parsed.getTime() - Date.now()) / 60000)
    if (diffMinutes <= 0) return 'сейчас'
    if (diffMinutes < 60) return `через ${diffMinutes} мин`
    const diffHours = Math.floor(diffMinutes / 60)
    const remainMinutes = diffMinutes % 60
    if (remainMinutes === 0) return `через ${diffHours} ч`
    return `через ${diffHours} ч ${remainMinutes} мин`
  }

  function statusVariant(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
    const normalized = String(status ?? '').trim().toLowerCase()
    if (normalized === 'completed') return 'success'
    if (normalized === 'running' || normalized === 'accepted') return 'info'
    if (normalized === 'failed' || normalized === 'cancelled') return 'danger'
    return 'secondary'
  }

  function controlModeLabel(controlMode: string | null | undefined): string {
    const normalized = String(controlMode ?? '').trim().toLowerCase()
    if (normalized === 'manual') return 'ручной'
    if (normalized === 'semi') return 'полуавто'
    return 'авто'
  }

  function laneLabel(taskType: string | null | undefined): string {
    const normalized = String(taskType ?? '').trim().toLowerCase()
    if (normalized === 'irrigation') return 'Полив'
    if (normalized === 'lighting') return 'Свет'
    if (normalized === 'climate') return 'Климат'
    if (normalized === 'solution_change') return 'Смена раствора'
    if (normalized === 'diagnostics') return 'Диагностика'
    if (normalized === 'mist') return 'Туман'
    return normalized || '—'
  }

  function timelinePrimaryLabel(step: ExecutionRun['timeline'][number] | null | undefined): string {
    if (!step) return 'событие'

    const details = isRecord(step.details) ? step.details : null
    const candidates = [
      step.reason_code,
      step.stage,
      asNonEmptyString(details?.stage),
      asNonEmptyString(details?.current_stage),
      step.status,
      step.decision,
      step.error_code,
      step.reason,
    ]

    for (const candidate of candidates) {
      const normalized = asNonEmptyString(candidate)
      if (normalized) return normalized
    }

    return 'событие'
  }

  function collapseTimeline(items: ExecutionRun['timeline'] = []): TimelineDisplayItem[] {
    const result: TimelineDisplayItem[] = []

    for (const step of items) {
      const label = timelinePrimaryLabel(step)
      const detail = timelineDetail(step, label)
      const previous = result[result.length - 1]

      if (step.event_type === 'AE_TASK_STARTED' && previous?.event_type === 'AE_TASK_STARTED') {
        previous.grouped = true
        previous.at = step.at
        previous.label = previous.label === label ? label : `${previous.label} -> ${label}`
        previous.detail = detail ?? previous.detail ?? 'Переходы стадий AE'
        continue
      }

      result.push({
        key: String(step.event_id ?? `${step.event_type}-${step.at ?? result.length}`),
        event_type: step.event_type,
        at: step.at,
        label,
        detail,
      })
    }

    return result.slice(-8)
  }

  function timelineDetail(step: ExecutionRun['timeline'][number] | null | undefined, label: string): string | null {
    if (!step) return null

    const reason = asNonEmptyString(step.reason)
    if (reason && reason !== label) return reason

    const errorCode = asNonEmptyString(step.error_code)
    if (errorCode && errorCode !== label) return errorCode

    if (step.event_type === 'AE_TASK_STARTED') {
      return 'Переход стадии automation-engine'
    }

    return null
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
  }

  function asNonEmptyString(value: unknown): string | null {
    return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
  }

  return {
    horizon,
    workspace,
    automationState,
    selectedExecution,
    diagnostics,
    loading,
    detailLoading,
    diagnosticsLoading,
    error,
    diagnosticsError,
    updatedAt,
    lanes,
    windows,
    laneWindows,
    recentRuns,
    activeRun,
    latestFailure,
    executionCounters,
    nextExecutableWindows,
    configOnlyLanes,
    activeProcessLabels,
    attentionItems,
    condensedTimeline,
    fetchWorkspace,
    fetchAutomationState,
    fetchExecution,
    fetchDiagnostics,
    setHorizon,
    clearDiagnostics,
    clearPollTimer,
    schedulePoll,
    pollCycle,
    handleVisibilityChange,
    formatDateTime,
    formatRelativeTrigger,
    statusVariant,
    controlModeLabel,
    laneLabel,
  }
}
