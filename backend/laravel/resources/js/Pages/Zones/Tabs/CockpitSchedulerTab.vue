<template>
  <div
    class="space-y-3"
    data-testid="scheduler-cockpit-root"
  >
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

    <CockpitLayout>
      <template #left>
        <HeroCountdown
          :run="activeRun"
          :lane-label="activeLaneLabel"
          :stage-label="activeStageLabel"
          :eta-label="etaLabel"
          :eta-hint="etaHint"
          :end-at="activeEndAt"
        />
        <NextUpCard
          :windows="nextExecutableWindows"
          :lane-label="laneLabel"
          :format-date-time="formatDateTime"
          :format-relative="formatRelativeTrigger"
        />
        <ConfigOnlyFooter :lanes="configOnlyLanesLabels" />
      </template>

      <template #center>
        <KpiRow
          :counters="executionCounters"
          :executable-windows-count="nextExecutableWindows.length"
          :runtime="workspace?.control?.automation_runtime"
          :window-type-count="windowTypeCount"
        />
        <SwimlaneTimeline
          :lanes="lanesHistory"
          :horizon="horizon"
        />
        <RecentRunsTable
          :runs="recentRuns"
          :selected-id="selectedExecution?.execution_id ?? null"
          :lane-label="laneLabel"
          :decision-label="decisionLabelForRun"
          @select="fetchExecution"
        />
      </template>

      <template #right>
        <SchedulerAttentionPanel
          v-if="attentionItems.length > 0"
          :items="attentionItems"
        />
        <CausalChainPanel
          v-if="selectedExecution"
          :run="selectedExecution"
          :error-text="selectedExecutionErrorMessage"
          :format-date-time="formatDateTime"
          :lane-label="laneLabel"
          @close="clearSelectedExecution"
          @retry="handleRetry"
          @open-events="handleOpenEvents"
        />
      </template>
    </CockpitLayout>

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
import { router } from '@inertiajs/vue3'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { ChainStep, ExecutionRun, LaneHistory } from '@/composables/zoneScheduleWorkspaceTypes'
import { deriveLaneHistory } from '@/composables/deriveLaneHistory'
import { useSchedulerHotkeys } from '@/composables/useSchedulerHotkeys'
import { subscribeToExecutionChain, type SchedulerChainSubscription } from '@/ws/schedulerChainChannel'
import SchedulerHeader from '@/Components/Scheduler/SchedulerHeader.vue'
import SchedulerAttentionPanel from '@/Components/Scheduler/SchedulerAttentionPanel.vue'
import SchedulerDiagnostics from '@/Components/Scheduler/SchedulerDiagnostics.vue'
import CockpitLayout from '@/Components/Scheduler/Cockpit/CockpitLayout.vue'
import HeroCountdown from '@/Components/Scheduler/Cockpit/HeroCountdown.vue'
import NextUpCard from '@/Components/Scheduler/Cockpit/NextUpCard.vue'
import ConfigOnlyFooter from '@/Components/Scheduler/Cockpit/ConfigOnlyFooter.vue'
import KpiRow from '@/Components/Scheduler/Cockpit/KpiRow.vue'
import SwimlaneTimeline from '@/Components/Scheduler/Cockpit/SwimlaneTimeline.vue'
import RecentRunsTable from '@/Components/Scheduler/Cockpit/RecentRunsTable.vue'
import CausalChainPanel from '@/Components/Scheduler/Cockpit/CausalChainPanel.vue'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
const { canDiagnose } = useRole()
const {
  horizon,
  workspace,
  selectedExecution,
  diagnostics,
  loading,
  diagnosticsLoading,
  error,
  diagnosticsError,
  recentRuns,
  activeRun,
  executionCounters,
  nextExecutableWindows,
  configOnlyLanes,
  attentionItems,
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
  controlModeLabel,
  laneLabel,
  workflowStageLabel,
  decisionLabel,
} = useZoneScheduleWorkspace(props, { showToast })

const zoneId = computed(() => props.zoneId)

const lanesHistory = computed<LaneHistory[]>(() => {
  if (workspace.value?.lanes_history?.length) {
    return workspace.value.lanes_history
  }
  return deriveLaneHistory(recentRuns.value, horizon.value)
})

const configOnlyLanesLabels = computed(() =>
  configOnlyLanes.value.map((lane) => ({
    task_type: lane.task_type,
    label: lane.label ?? laneLabel(lane.task_type),
  })),
)

const windowTypeCount = computed(() => {
  const seen = new Set<string>()
  for (const w of nextExecutableWindows.value) {
    if (w.task_type) seen.add(w.task_type)
  }
  return seen.size
})

const activeLaneLabel = computed<string | null>(() => {
  const run = activeRun.value
  if (!run) return null
  return laneLabel(run.schedule_task_type ?? run.task_type)
})

const activeStageLabel = computed<string | null>(() => {
  const run = activeRun.value
  if (!run) return null
  return (
    workflowStageLabel(run.current_stage ?? run.workflow_phase ?? null) ??
    run.current_stage ??
    run.workflow_phase ??
    null
  )
})

const etaLabel = computed<string>(() => {
  const run = activeRun.value
  if (!run) return '—'
  if (run.due_at) return formatRelativeTrigger(run.due_at)
  if (run.expires_at) return formatRelativeTrigger(run.expires_at)
  return '—'
})

const activeEndAt = computed<string | null>(() => {
  const run = activeRun.value
  if (!run) return null
  return run.due_at ?? run.expires_at ?? null
})

const etaHint = computed<string>(() => {
  const run = activeRun.value
  if (!run?.due_at && !run?.expires_at) return 'длительность не задана'
  return 'осталось до завершения'
})

const selectedExecutionErrorMessage = computed<string | null>(() =>
  resolveHumanErrorMessage({
    code: selectedExecution.value?.error_code,
    message: selectedExecution.value?.error_message,
    humanMessage: selectedExecution.value?.human_error_message,
  }),
)

function decisionLabelForRun(run: ExecutionRun): string {
  const outcome = decisionLabel(run.decision_outcome, run.decision_degraded)
  const reason = run.decision_reason_code ? ` · ${run.decision_reason_code}` : ''
  return outcome ? `${outcome}${reason}` : (run.status ?? 'UNKNOWN')
}

function clearSelectedExecution(): void {
  selectedExecution.value = null
}

function handleRetry(executionId: string): void {
  showToast(`Повтор исполнения #${executionId} пока не реализован.`, 'info')
}

function handleOpenEvents(executionId: string): void {
  if (typeof window === 'undefined') return
  router.visit(`/zones/${props.zoneId}?tab=events&execution_id=${executionId}`)
}

function applyChainStep(executionId: string, step: ChainStep): void {
  if (selectedExecution.value?.execution_id === executionId) {
    const current = selectedExecution.value.chain ?? []
    selectedExecution.value = {
      ...selectedExecution.value,
      chain: [...current, step],
    }
  }
  if (activeRun.value?.execution_id === executionId) {
    const current = activeRun.value.chain ?? []
    activeRun.value.chain = [...current, step]
  }
}

function moveSelection(delta: 1 | -1): void {
  const runs = recentRuns.value
  if (runs.length === 0) return

  const currentId = selectedExecution.value?.execution_id ?? null
  const currentIndex = currentId
    ? runs.findIndex((run) => run.execution_id === currentId)
    : -1

  let nextIndex: number
  if (currentIndex === -1) {
    nextIndex = delta === 1 ? 0 : runs.length - 1
  } else {
    nextIndex = Math.min(runs.length - 1, Math.max(0, currentIndex + delta))
  }

  const next = runs[nextIndex]
  if (next) {
    void fetchExecution(next.execution_id)
  }
}

useSchedulerHotkeys({
  onNext: () => moveSelection(1),
  onPrev: () => moveSelection(-1),
  onOpen: () => {
    const first = selectedExecution.value ?? recentRuns.value[0]
    if (first) {
      void fetchExecution(first.execution_id)
    }
  },
  onRefresh: () => {
    void refreshWorkspace()
  },
  onClose: () => {
    if (selectedExecution.value) clearSelectedExecution()
  },
})

let chainSubscription: SchedulerChainSubscription | null = null

function resubscribeChain(): void {
  chainSubscription?.unsubscribe()
  chainSubscription = null
  const zoneId = props.zoneId
  if (zoneId === null || zoneId === undefined) return
  chainSubscription = subscribeToExecutionChain(zoneId, {
    onStep: (executionId, step) => applyChainStep(executionId, step),
  })
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
  resubscribeChain()
  if (import.meta.env.MODE !== 'test' && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
})

onUnmounted(() => {
  clearPollTimer()
  chainSubscription?.unsubscribe()
  chainSubscription = null
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
})

watch(
  () => props.zoneId,
  () => {
    void refreshWorkspace()
    resubscribeChain()
  },
)
</script>
