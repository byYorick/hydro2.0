import { computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import type { AutomationLogicMode } from '@/composables/zoneAutomationUtils'
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
}

export function useZoneAutomationScheduler(props: ZoneAutomationTabProps, deps: ZoneAutomationSchedulerDeps) {
  const { get } = deps

  // ─── Refs ──────────────────────────────────────────────────────────────────
  const schedulerTaskIdInput = ref('')
  const schedulerTaskLookupLoading = ref(false)
  const schedulerTaskListLoading = ref(false)
  const schedulerTaskError = ref<string | null>(null)
  const schedulerTaskStatus = ref<SchedulerTaskStatus | null>(null)
  const recentSchedulerTasks = ref<SchedulerTaskStatus[]>([])
  const schedulerTaskSearch = ref('')
  const schedulerTaskPreset = ref<SchedulerTaskPreset>('all')
  const schedulerTasksUpdatedAt = ref<string | null>(null)
  let schedulerTasksPollTimer: ReturnType<typeof setTimeout> | null = null
  let schedulerTaskListRequestVersion = 0
  let schedulerTaskLookupRequestVersion = 0

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

      const items = Array.isArray((response.data as SchedulerTasksResponse)?.data)
        ? (response.data as SchedulerTasksResponse).data!
        : []
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

  async function lookupSchedulerTask(taskIdRaw?: string): Promise<void> {
    if (!props.zoneId) return

    const taskId = normalizeTaskId(taskIdRaw)
    if (!taskId) {
      schedulerTaskStatus.value = null
      schedulerTaskError.value = 'Укажите task_id вида st-...'
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
      const err = error as { response?: { data?: { message?: string } } }
      schedulerTaskError.value = err?.response?.data?.message ?? 'Не удалось получить статус задачи.'
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
  }

  return {
    // State
    schedulerTaskIdInput,
    schedulerTaskLookupLoading,
    schedulerTaskListLoading,
    schedulerTaskError,
    schedulerTaskStatus,
    recentSchedulerTasks,
    filteredRecentSchedulerTasks,
    schedulerTaskSearch,
    schedulerTaskPreset,
    schedulerTaskPresetOptions,
    schedulerTasksUpdatedAt,
    // Actions
    fetchRecentSchedulerTasks,
    lookupSchedulerTask,
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
