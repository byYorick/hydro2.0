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
        <section
          v-if="selectedExecution"
          class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3.5"
          data-testid="scheduler-chain-placeholder"
        >
          <header class="flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-2">
                <span class="font-mono text-[13px] font-bold text-[color:var(--text-primary)]">
                  #{{ selectedExecution.execution_id }}
                </span>
                <span class="text-[11px] text-[color:var(--text-dim)]">
                  {{ laneLabel(selectedExecution.schedule_task_type ?? selectedExecution.task_type) }}
                </span>
              </div>
              <p class="mt-1 text-[11px] text-[color:var(--text-muted)]">
                Причинно-следственная цепочка будет доступна в Фазе 2 redesign.
              </p>
            </div>
            <button
              type="button"
              class="rounded-md border border-[color:var(--border-muted)] px-2 py-1 text-[11px] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]"
              data-testid="scheduler-chain-close"
              @click="clearSelectedExecution"
            >
              ✕
            </button>
          </header>
        </section>
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
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { ExecutionRun, LaneHistory } from '@/composables/zoneScheduleWorkspaceTypes'
import { deriveLaneHistory } from '@/composables/deriveLaneHistory'
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

const etaHint = computed<string>(() => {
  const run = activeRun.value
  if (!run?.due_at && !run?.expires_at) return 'длительность не задана'
  return 'осталось до завершения'
})

function decisionLabelForRun(run: ExecutionRun): string {
  const outcome = decisionLabel(run.decision_outcome, run.decision_degraded)
  const reason = run.decision_reason_code ? ` · ${run.decision_reason_code}` : ''
  return outcome ? `${outcome}${reason}` : (run.status ?? 'UNKNOWN')
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
