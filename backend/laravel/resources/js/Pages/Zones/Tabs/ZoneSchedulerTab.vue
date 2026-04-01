<template>
  <div class="space-y-6">
    <SchedulerHeader
      :zone-id="zoneId"
      :horizon="horizon"
      :loading="loading"
      :error="error"
      :counters="executionCounters"
      :executable-windows-count="nextExecutableWindows.length"
      :has-active-run="Boolean(activeRun)"
      :control-mode="workspace?.control?.control_mode"
      :control-mode-label="controlModeLabel"
      :status-variant="statusVariant"
      @change-horizon="changeHorizon"
      @refresh="refreshWorkspace"
    />

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div class="space-y-6">
        <SchedulerCurrentStateCard
          :updated-at="updatedAt"
          :format-date-time="formatDateTime"
          :active-run="activeRun"
          :automation-state="automationState"
          :workspace-control-mode="workspace?.control?.control_mode"
          :active-process-labels="activeProcessLabels"
          :status-variant="statusVariant"
          :control-mode-label="controlModeLabel"
          :lane-label="laneLabel"
          :decision-variant="decisionVariant"
          :decision-label="decisionLabel"
          :decision-reason-label="decisionReasonLabel"
        />

        <SchedulerAttentionPanel
          :items="attentionItems"
          :attention-card-class="attentionCardClass"
        />

        <SchedulerExecutableWindows
          :windows="nextExecutableWindows"
          :timezone="workspace?.control?.timezone"
          :config-only-lanes="configOnlyLanes"
          :lane-label="laneLabel"
          :format-date-time="formatDateTime"
          :format-relative-trigger="formatRelativeTrigger"
        />
      </div>

      <div class="space-y-6">
        <SchedulerRunsPanel
          :runtime="workspace?.control?.automation_runtime"
          :active-run="activeRun"
          :active-run-decision-summary="activeRunDecisionSummary"
          :recent-runs="recentRuns"
          :selected-execution-id="selectedExecution?.execution_id ?? null"
          :lane-label="laneLabel"
          :status-variant="statusVariant"
          :decision-variant="decisionVariant"
          :decision-label="decisionLabel"
          :format-date-time="formatDateTime"
          :decision-summary="decisionSummary"
          @select-run="fetchExecution"
        />

        <SchedulerRunDetail
          :detail-loading="detailLoading"
          :selected-execution="selectedExecution"
          :condensed-timeline="condensedTimeline"
          :selected-execution-error-message="selectedExecutionErrorMessage"
          :selected-execution-decision-summary="selectedExecutionDecisionSummary"
          :lane-label="laneLabel"
          :status-variant="statusVariant"
          :decision-variant="decisionVariant"
          :decision-label="decisionLabel"
          :format-date-time="formatDateTime"
        />
      </div>
    </div>

    <SchedulerDiagnostics
      :can-diagnose="canDiagnose"
      :diagnostics-available="Boolean(workspace?.capabilities?.diagnostics_available)"
      :diagnostics-loading="diagnosticsLoading"
      :diagnostics-error="diagnosticsError"
      :diagnostics="diagnostics"
      :status-variant="statusVariant"
      :lane-label="laneLabel"
      :format-date-time="formatDateTime"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import SchedulerHeader from '@/Components/Scheduler/SchedulerHeader.vue'
import SchedulerCurrentStateCard from '@/Components/Scheduler/SchedulerCurrentStateCard.vue'
import SchedulerAttentionPanel from '@/Components/Scheduler/SchedulerAttentionPanel.vue'
import SchedulerExecutableWindows from '@/Components/Scheduler/SchedulerExecutableWindows.vue'
import SchedulerRunsPanel from '@/Components/Scheduler/SchedulerRunsPanel.vue'
import SchedulerRunDetail from '@/Components/Scheduler/SchedulerRunDetail.vue'
import SchedulerDiagnostics from '@/Components/Scheduler/SchedulerDiagnostics.vue'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
const { get } = useApi(showToast)
const { canDiagnose } = useRole()
const {
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
  recentRuns,
  activeRun,
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
  handleVisibilityChange,
  formatDateTime,
  formatRelativeTrigger,
  statusVariant,
  controlModeLabel,
  laneLabel,
  decisionLabel,
  decisionReasonLabel,
  describeDecision,
} = useZoneScheduleWorkspace(props, { get, showToast })

const zoneId = computed(() => props.zoneId)
const selectedExecutionErrorMessage = computed(() => resolveHumanErrorMessage({
  code: selectedExecution.value?.error_code,
  message: selectedExecution.value?.error_message,
  humanMessage: selectedExecution.value?.human_error_message,
}))
const activeRunDecisionSummary = computed(() => decisionSummary(activeRun.value))
const selectedExecutionDecisionSummary = computed(() => decisionSummary(selectedExecution.value))

function attentionCardClass(tone: 'danger' | 'warning' | 'info'): string {
  if (tone === 'danger') return 'border-red-200 bg-red-50/70'
  if (tone === 'warning') return 'border-amber-200 bg-amber-50/70'
  return 'border-sky-200 bg-sky-50/70'
}

function decisionVariant(
  outcome: string | null | undefined,
  degraded: boolean | null | undefined,
): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
  const normalized = String(outcome ?? '').trim().toLowerCase()
  if (normalized === 'skip') return 'secondary'
  if (normalized === 'fail') return 'danger'
  if (degraded) return 'warning'
  if (normalized === 'run' || normalized === 'degraded_run') return 'info'
  return 'secondary'
}

function decisionSummary(execution: {
  decision_outcome?: string | null
  decision_degraded?: boolean | null
  decision_reason_code?: string | null
  error_code?: string | null
  replay_count?: number | null
} | null | undefined): string | null {
  if (!execution) return null

  const detail = describeDecision({
    outcome: execution.decision_outcome,
    degraded: execution.decision_degraded,
    reasonCode: execution.decision_reason_code,
    errorCode: execution.error_code,
  })
  const replayCount = typeof execution.replay_count === 'number' ? execution.replay_count : 0
  const replayLabel = replayCount > 0 ? `Setup replay: ${replayCount}` : null

  return [detail, replayLabel].filter((part): part is string => Boolean(part && part.trim() !== '')).join(' · ') || null
}

function changeHorizon(nextHorizon: '24h' | '7d'): void {
  if (horizon.value === nextHorizon) return
  setHorizon(nextHorizon)
  void refreshWorkspace()
}

async function refreshWorkspace(): Promise<void> {
  await Promise.all([
    fetchWorkspace(),
    fetchAutomationState({ silent: true }),
  ])

  if (canDiagnose.value && workspace.value?.capabilities?.diagnostics_available) {
    await fetchDiagnostics({ silent: true })
  } else {
    clearDiagnostics()
  }

  schedulePoll()
}

onMounted(() => {
  void refreshWorkspace()
  if (import.meta.env.MODE !== 'test' && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
})

onUnmounted(() => {
  clearPollTimer()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
})

watch(
  () => props.zoneId,
  () => {
    void refreshWorkspace()
  }
)
</script>
