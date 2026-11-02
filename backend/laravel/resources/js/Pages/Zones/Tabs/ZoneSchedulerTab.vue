<template>
  <div
    class="scheduler-workspace space-y-3 p-2 md:p-3"
    data-testid="scheduler-root"
  >
    <SchedulerHeader
      :zone-id="zoneId"
      :horizon="horizon"
      :loading="loading"
      :error="error"
      :has-active-run="Boolean(activeRun)"
      :control-mode="workspace?.control?.control_mode"
      :control-mode-label="controlModeLabel"
      :status-variant="statusVariant"
      :updated-label="updatedAt ? formatDateTime(updatedAt) : null"
      @manage-schedules="activeView = 'schedules'"
      @change-horizon="changeHorizon"
      @refresh="refreshWorkspace"
    />

    <Tabs
      v-model="activeView"
      :tabs="viewTabs"
      list-role="group"
      aria-label="Разделы планировщика"
    />
    <KpiRow
      :counters="executionCounters"
      :executable-windows-count="executableWindows.length"
      :runtime="workspace?.control?.automation_runtime"
      :window-type-count="windowTypeCount"
    />
    <CockpitLayout>
      <template #left>
        <HeroCountdown
          :run="activeRun"
          :lane-label="activeLaneLabel"
          :stage-label="activeStageLabel"
          :eta-label="etaLabel"
          :eta-hint="etaHint"
          :eta-estimated="activeEtaEstimated"
          :end-at="activeEndAt"
          :format-date-time="formatDateTime"
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
        <SwimlaneTimeline
          v-if="activeView === 'overview'"
          :lanes="lanesHistory"
          :horizon="horizon"
          :format-date-time="formatDateTime"
        />
        <ManualSchedulesSection
          v-show="activeView === 'schedules'"
          :zone-id="zoneId"
          :schedules="manualSchedules"
          :loading="loading"
          :can-manage="canManageManualSchedules"
          :lane-label="laneLabel"
          :executable-task-types="workspace?.capabilities?.executable_task_types ?? []"
          :plan-windows="workspace?.plan?.windows ?? []"
          @changed="refreshWorkspace"
        />
        <RecentRunsTable
          v-if="activeView !== 'schedules'"
          :runs="activeView === 'history' ? recentRuns : recentRuns.slice(0, 5)"
          :show-filters="activeView === 'history'"
          :selected-id="selectedExecutionId"
          :lane-label="laneLabel"
          :decision-label="decisionLabelForRun"
          @visible-runs="navigationRuns = $event"
          @select="selectExecution"
        />
      </template>

      <template #right>
        <p
          v-if="detailLoading && activeView !== 'schedules'"
          role="status"
          class="p-4 text-sm text-[color:var(--text-muted)]"
        >
          Загружаем детали выполнения…
        </p>
        <div
          v-if="detailError && activeView !== 'schedules'"
          role="alert"
          class="rounded-xl border border-status-critical p-3 text-sm text-status-critical"
        >
          {{ detailError }}
          <Button
            v-if="selectedExecutionId"
            size="sm"
            variant="ghost"
            @click="selectExecution(selectedExecutionId)"
          >
            Повторить загрузку
          </Button>
        </div>
        <SchedulerAttentionPanel
          v-if="attentionAlerts.length > 0 || attentionStatus.length > 0"
          :alert-items="attentionAlerts"
          :status-items="attentionStatus"
        />
        <CausalChainPanel
          v-if="selectedExecution && activeView !== 'schedules'"
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

    <details
      v-if="canDiagnose && workspace?.capabilities?.diagnostics_available"
      class="rounded-xl border border-[color:var(--border-muted)] p-3"
      @toggle="onDiagnosticsToggle"
    >
      <summary class="cursor-pointer text-sm font-medium">
        Диагностика планировщика
      </summary>
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
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { ExecutionRun, LaneHistory } from '@/composables/zoneScheduleWorkspaceTypes'
import { deriveLaneHistory } from '@/composables/deriveLaneHistory'
import { useSchedulerHotkeys } from '@/composables/useSchedulerHotkeys'
import { useSchedulerExecutionChain } from '@/composables/useSchedulerExecutionChain'
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
import ManualSchedulesSection from '@/Components/Scheduler/ManualSchedulesSection.vue'
import { api } from '@/services/api'
import Tabs from '@/Components/Tabs.vue'
import Button from '@/Components/Button.vue'
import { deriveRunEndAt, readRunDurationSec } from '@/utils/schedulerRunTime'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
const { canDiagnose, role } = useRole()
const {
  horizon,
  workspace,
  selectedExecution,
  selectedExecutionId,
  detailError,
  diagnostics,
  loading,
  diagnosticsLoading,
  error,
  diagnosticsError,
  recentRuns,
  activeRun,
  executionCounters,
  nextExecutableWindows,
  executableWindows,
  updatedAt,
  detailLoading,
  configOnlyLanes,
  manualSchedules,
  attentionAlerts,
  attentionStatus,
  refreshWorkspace: refreshWorkspaceData,
  fetchDiagnostics,
  selectExecution,
  clearSelectedExecution,
  setHorizon,
  clearDiagnostics,
  formatDateTime,
  formatRelativeTrigger,
  statusVariant,
  statusLabel,
  controlModeLabel,
  laneLabel,
  workflowStageLabel,
  decisionLabel,
} = useZoneScheduleWorkspace(props)

useSchedulerExecutionChain(() => props.zoneId, selectedExecution, workspace)
const zoneId = computed(() => props.zoneId)
const activeView = ref('overview')
const navigationRuns = ref<ExecutionRun[]>([])
const diagnosticsOpen = ref(false)
const viewTabs = computed(() => [
  { id: 'overview', label: 'Обзор', testId: 'scheduler-view-overview' },
  { id: 'schedules', label: 'Расписания', badge: manualSchedules.value.length, testId: 'scheduler-view-schedules' },
  { id: 'history', label: 'История', badge: recentRuns.value.length, testId: 'scheduler-view-history' },
])
function onDiagnosticsToggle(event: Event) {
  diagnosticsOpen.value = (event.target as HTMLDetailsElement).open
  if (diagnosticsOpen.value) void fetchDiagnostics()
}

const canManageManualSchedules = computed(() => role.value === 'agronomist' || role.value === 'admin')

const lanesHistory = computed<LaneHistory[]>(() => {
  if (workspace.value?.lanes_history?.length) {
    return workspace.value.lanes_history
  }
  return deriveLaneHistory(recentRuns.value, horizon.value, {
    windows: workspace.value?.plan?.windows ?? [],
    laneTypes: workspace.value?.plan?.lanes?.map((lane) => lane.task_type) ?? [],
  })
})

const configOnlyLanesLabels = computed(() =>
  configOnlyLanes.value.map((lane) => ({
    task_type: lane.task_type,
    label: lane.label ?? laneLabel(lane.task_type),
  })),
)

const windowTypeCount = computed(() => {
  const seen = new Set<string>()
  for (const w of executableWindows.value) {
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

const activeEndAt = computed<string | null>(() => {
  const run = activeRun.value
  if (!run) return null
  const endAt = deriveRunEndAt(run)
  return endAt ? endAt.toISOString() : null
})

const etaLabel = computed<string>(() => {
  const endAt = activeEndAt.value
  if (!endAt) return '—'
  return formatRelativeTrigger(endAt)
})

const etaHint = computed<string>(() => {
  return activeEndAt.value ? 'осталось до завершения' : 'длительность не задана'
})

const activeEtaEstimated = computed<boolean>(() => {
  const run = activeRun.value
  if (!run || !activeEndAt.value) return false
  // Duration-based ETA is always estimated; expires_at is authoritative when used.
  return readRunDurationSec(run) !== null
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

async function handleRetry(executionId: string): Promise<void> {
  try {
    const response = await api.zones.retryExecution<{ intent_id?: number; data?: { intent_id?: number } }>(
      Number(props.zoneId),
      executionId,
    )
    const intentId = response?.intent_id ?? response?.data?.intent_id
    showToast(
      intentId
        ? `Повтор исполнения #${executionId} создан (intent #${intentId}).`
        : `Повтор исполнения #${executionId} принят.`,
      'success',
    )
    await refreshWorkspace()
  } catch (error) {
    const message = resolveHumanErrorMessage({
      code: (error as { code?: string })?.code,
      message: (error as { message?: string })?.message,
      humanMessage: null,
    }) ?? 'Не удалось запустить повтор исполнения.'
    showToast(message, 'error')
  }
}

function handleOpenEvents(executionId: string): void {
  if (typeof window === 'undefined') return
  router.visit(`/zones/${props.zoneId}?tab=events&execution_id=${executionId}`)
}

function moveSelection(delta: 1 | -1): void {
  if (activeView.value === 'schedules') return
  const runs = navigationRuns.value
  if (runs.length === 0) return

  const currentId = selectedExecutionId.value
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
    selectExecution(next.execution_id)
  }
}

useSchedulerHotkeys({
  onNext: () => moveSelection(1),
  onPrev: () => moveSelection(-1),
  onOpen: () => {
    if (activeView.value === 'schedules') return
    const first = selectedExecution.value ?? navigationRuns.value[0]
    if (first) {
      selectExecution(first.execution_id)
    }
  },
  onRefresh: () => {
    void refreshWorkspace()
  },
  onClose: () => {
    if (selectedExecution.value) clearSelectedExecution()
  },
})

function changeHorizon(nextHorizon: '24h' | '7d'): void {
  if (horizon.value === nextHorizon) return
  setHorizon(nextHorizon)
  void refreshWorkspace()
}

async function refreshWorkspace(): Promise<void> {
  await refreshWorkspaceData()
  if (diagnosticsOpen.value && canDiagnose.value && workspace.value?.capabilities?.diagnostics_available) {
    await fetchDiagnostics({ silent: true })
  } else { clearDiagnostics() }
}

watch(
  () => props.zoneId,
  () => {
    diagnosticsOpen.value = false
  },
)
</script>

<style scoped>
.scheduler-workspace {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border-muted) 86%, transparent);
  border-radius: 1.6rem;
  background:
    radial-gradient(70% 46% at 18% 0%, color-mix(in srgb, var(--status-info) 12%, transparent), transparent 62%),
    radial-gradient(56% 45% at 98% 12%, color-mix(in srgb, var(--status-ok) 11%, transparent), transparent 66%),
    linear-gradient(180deg, color-mix(in srgb, var(--bg-surface) 96%, transparent), color-mix(in srgb, var(--bg-main) 88%, transparent));
  box-shadow: var(--shadow-card);
}

.scheduler-workspace::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background-image:
    linear-gradient(color-mix(in srgb, var(--text-dim) 7%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--text-dim) 6%, transparent) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.78), transparent 82%);
  pointer-events: none;
}
</style>
