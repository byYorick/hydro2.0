import { onMounted, onUnmounted, watch } from 'vue'
import { useCommands } from '@/composables/useCommands'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useZoneAutomationState } from '@/composables/useZoneAutomationState'
import { useZoneAutomationApi } from '@/composables/useZoneAutomationApi'
import { useZoneAutomationScheduler } from '@/composables/useZoneAutomationScheduler'

// Re-export all public types so existing consumers keep working without import changes
export type {
  PredictionTargets,
  ZoneAutomationTabProps,
  SchedulerTaskLifecycleItem,
  SchedulerTaskTimelineItem,
  SchedulerTaskProcessAction,
  SchedulerTaskProcessState,
  SchedulerTaskProcessStep,
  SchedulerTaskStatus,
  SchedulerTaskSlaVariant,
  SchedulerTaskSlaMeta,
  SchedulerTaskDoneMeta,
  SchedulerTaskPreset,
} from '@/composables/zoneAutomationTypes'

export type { AutomationLogicMode } from '@/composables/zoneAutomationUtils'

import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'

export function useZoneAutomationTab(props: ZoneAutomationTabProps) {
  const { showToast } = useToast()
  const { sendZoneCommand } = useCommands(showToast)
  const { get, post } = useApi(showToast)

  const state = useZoneAutomationState(props, { sendZoneCommand, showToast })
  const api = useZoneAutomationApi(props, state, { get, post, showToast, sendZoneCommand })
  const scheduler = useZoneAutomationScheduler(props, { get, post, showToast })

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  onMounted(() => {
    void api.hydrateAutomationProfileFromCurrentZone({ includeTargets: true })
    void scheduler.fetchAutomationControlMode()
    void scheduler.fetchRecentSchedulerTasks()
    if (import.meta.env.MODE !== 'test') {
      void scheduler.pollSchedulerTasksCycle()
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', scheduler.handleVisibilityChange)
      }
    }
  })

  onUnmounted(() => {
    scheduler.clearSchedulerTasksPollTimer()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', scheduler.handleVisibilityChange)
    }
  })

  // ─── Zone change coordination ──────────────────────────────────────────────

  watch(
    () => props.zoneId,
    () => {
      state.pendingTargetsSyncForZoneChange.value = true
      scheduler.resetForZoneChange()
      void api.hydrateAutomationProfileFromCurrentZone({ includeTargets: false })
      void scheduler.fetchAutomationControlMode()
      void scheduler.fetchRecentSchedulerTasks()
      scheduler.scheduleSchedulerTasksPoll()
    }
  )

  return {
    // State
    role: state.role,
    canConfigureAutomation: state.canConfigureAutomation,
    canOperateAutomation: state.canOperateAutomation,
    isSystemTypeLocked: state.isSystemTypeLocked,
    climateForm: state.climateForm,
    waterForm: state.waterForm,
    lightingForm: state.lightingForm,
    quickActions: state.quickActions,
    isApplyingProfile: state.isApplyingProfile,
    isSyncingAutomationLogicProfile: state.isSyncingAutomationLogicProfile,
    lastAppliedAt: state.lastAppliedAt,
    automationLogicMode: state.automationLogicMode,
    lastAutomationLogicSyncAt: state.lastAutomationLogicSyncAt,
    predictionTargets: state.predictionTargets,
    telemetryLabel: state.telemetryLabel,
    waterTopologyLabel: state.waterTopologyLabel,
    resetToRecommended: state.resetToRecommended,
    runManualIrrigation: state.runManualIrrigation,
    runManualClimate: state.runManualClimate,
    runManualLighting: state.runManualLighting,
    runManualPh: state.runManualPh,
    runManualEc: state.runManualEc,
    // Api
    applyAutomationProfile: api.applyAutomationProfile,
    // Scheduler
    schedulerTaskIdInput: scheduler.schedulerTaskIdInput,
    schedulerTaskLookupLoading: scheduler.schedulerTaskLookupLoading,
    schedulerTaskListLoading: scheduler.schedulerTaskListLoading,
    schedulerTaskError: scheduler.schedulerTaskError,
    schedulerTaskStatus: scheduler.schedulerTaskStatus,
    automationControlMode: scheduler.automationControlMode,
    allowedManualSteps: scheduler.allowedManualSteps,
    automationControlModeLoading: scheduler.automationControlModeLoading,
    automationControlModeSaving: scheduler.automationControlModeSaving,
    manualStepLoading: scheduler.manualStepLoading,
    recentSchedulerTasks: scheduler.recentSchedulerTasks,
    filteredRecentSchedulerTasks: scheduler.filteredRecentSchedulerTasks,
    schedulerTaskSearch: scheduler.schedulerTaskSearch,
    schedulerTaskPreset: scheduler.schedulerTaskPreset,
    schedulerTaskPresetOptions: scheduler.schedulerTaskPresetOptions,
    schedulerTasksUpdatedAt: scheduler.schedulerTasksUpdatedAt,
    fetchRecentSchedulerTasks: scheduler.fetchRecentSchedulerTasks,
    fetchAutomationControlMode: scheduler.fetchAutomationControlMode,
    lookupSchedulerTask: scheduler.lookupSchedulerTask,
    setAutomationControlMode: scheduler.setAutomationControlMode,
    runManualStep: scheduler.runManualStep,
    schedulerTaskStatusVariant: scheduler.schedulerTaskStatusVariant,
    schedulerTaskStatusLabel: scheduler.schedulerTaskStatusLabel,
    schedulerTaskProcessStatusVariant: scheduler.schedulerTaskProcessStatusVariant,
    schedulerTaskProcessStatusLabel: scheduler.schedulerTaskProcessStatusLabel,
    schedulerTaskEventLabel: scheduler.schedulerTaskEventLabel,
    schedulerTaskTimelineStageLabel: scheduler.schedulerTaskTimelineStageLabel,
    schedulerTaskTimelineStepLabel: scheduler.schedulerTaskTimelineStepLabel,
    schedulerTaskTimelineItems: scheduler.schedulerTaskTimelineItems,
    schedulerTaskDecisionLabel: scheduler.schedulerTaskDecisionLabel,
    schedulerTaskReasonLabel: scheduler.schedulerTaskReasonLabel,
    schedulerTaskErrorLabel: scheduler.schedulerTaskErrorLabel,
    schedulerTaskSlaMeta: scheduler.schedulerTaskSlaMeta,
    schedulerTaskDoneMeta: scheduler.schedulerTaskDoneMeta,
    formatDateTime: scheduler.formatDateTime,
  }
}
