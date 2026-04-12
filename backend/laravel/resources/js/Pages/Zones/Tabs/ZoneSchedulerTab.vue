<template>
  <div class="space-y-3">
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

    <!-- Живая строка состояния -->
    <SchedulerStatusStrip
      :updated-at="updatedAt"
      :format-date-time="formatDateTime"
      :active-run="activeRun"
      :automation-state="automationState"
      :active-process-labels="activeProcessLabels"
      :lane-label="laneLabel"
      :decision-variant="decisionVariant"
      :decision-label="decisionLabel"
    />

    <!-- Алерты danger — поверх всего -->
    <SchedulerAttentionPanel
      v-if="dangerItems.length > 0"
      :items="dangerItems"
    />

    <!-- Один столбец -->
    <div class="space-y-3">
      <SchedulerNextWindow
        :windows="nextExecutableWindows"
        :timezone="workspace?.control?.timezone"
        :config-only-lanes="configOnlyLanes"
        :lane-label="laneLabel"
        :mode-label="modeLabel"
        :format-date-time="formatDateTime"
        :format-relative-trigger="formatRelativeTrigger"
      />

      <SchedulerAttentionPanel
        v-if="dangerItems.length === 0 && softItems.length > 0"
        :items="softItems"
      />

      <SchedulerRunsColumn
        :runtime="workspace?.control?.automation_runtime"
        :active-run="activeRun"
        :active-run-decision-summary="activeRunDecisionSummary"
        :recent-runs="recentRuns"
        :selected-execution="selectedExecution"
        :detail-loading="detailLoading"
        :condensed-timeline="condensedTimeline"
        :selected-execution-error-message="selectedExecutionErrorMessage"
        :selected-execution-decision-summary="selectedExecutionDecisionSummary"
        :lane-label="laneLabel"
        :stage-label="workflowStageLabel"
        :status-variant="statusVariant"
        :status-label="statusLabel"
        :event-type-label="eventTypeLabel"
        :decision-variant="decisionVariant"
        :decision-label="decisionLabel"
        :format-date-time="formatDateTime"
        :decision-summary="decisionSummary"
        @select-run="fetchExecution"
        @close-detail="clearSelectedExecution"
      />
    </div>

    <!-- Диагностика — аккордеон внизу -->
    <SchedulerDiagnostics
      :can-diagnose="canDiagnose"
      :diagnostics-available="Boolean(workspace?.capabilities?.diagnostics_available)"
      :diagnostics-loading="diagnosticsLoading"
      :diagnostics-error="diagnosticsError"
      :diagnostics="diagnostics"
      :status-variant="statusVariant"
      :status-label="statusLabel"
      :lane-label="laneLabel"
      :format-date-time="formatDateTime"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import SchedulerHeader from '@/Components/Scheduler/SchedulerHeader.vue'
import SchedulerStatusStrip from '@/Components/Scheduler/SchedulerStatusStrip.vue'
import SchedulerAttentionPanel from '@/Components/Scheduler/SchedulerAttentionPanel.vue'
import SchedulerNextWindow from '@/Components/Scheduler/SchedulerNextWindow.vue'
import SchedulerRunsColumn from '@/Components/Scheduler/SchedulerRunsColumn.vue'
import SchedulerDiagnostics from '@/Components/Scheduler/SchedulerDiagnostics.vue'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
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
  statusLabel,
  modeLabel,
  eventTypeLabel,
  controlModeLabel,
  laneLabel,
  workflowStageLabel,
  decisionLabel,
  describeDecision,
} = useZoneScheduleWorkspace(props, { showToast })

const zoneId = computed(() => props.zoneId)

const selectedExecutionErrorMessage = computed(() =>
  resolveHumanErrorMessage({
    code: selectedExecution.value?.error_code,
    message: selectedExecution.value?.error_message,
    humanMessage: selectedExecution.value?.human_error_message,
  }),
)
const activeRunDecisionSummary = computed(() => decisionSummary(activeRun.value))
const selectedExecutionDecisionSummary = computed(() => decisionSummary(selectedExecution.value))

// Разделяем attention items на danger и остальные
const dangerItems = computed(() =>
  attentionItems.value.filter((i) => i.tone === 'danger'),
)
const softItems = computed(() =>
  attentionItems.value.filter((i) => i.tone !== 'danger'),
)

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
  const replayLabel = replayCount > 0 ? `Replay: ${replayCount}` : null

  return (
    [detail, replayLabel]
      .filter((part): part is string => Boolean(part && part.trim() !== ''))
      .join(' · ') || null
  )
}

function clearSelectedExecution(): void {
  selectedExecution.value = null
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
  },
)
</script>
