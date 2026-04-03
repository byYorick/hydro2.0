<template>
  <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Что происходит сейчас</h4>
        <p class="text-sm text-[color:var(--text-dim)]">
          Снимок фактического состояния зоны из canonical automation state.
        </p>
      </div>
      <div class="text-xs text-[color:var(--text-muted)]">
        Sync: {{ updatedAt ? formatDateTime(updatedAt) : '—' }}
      </div>
    </div>

    <div class="mt-4 rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 p-4">
      <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span
              class="ui-state-dot"
              :class="statusDotColor"
              :title="activeRun ? `run ${activeRun.status || 'unknown'}` : 'idle'"
            />
            <Badge :variant="activeRun ? statusVariant(activeRun.status) : 'secondary'">
              {{ activeRun ? activeRun.status : 'idle' }}
            </Badge>
            <Badge variant="secondary">
              {{ controlModeLabel(controlModeResolved) }}
            </Badge>
            <Badge
              v-if="decisionOutcome"
              :variant="decisionVariant(decisionOutcome, decisionDegraded)"
            >
              {{ decisionLabel(decisionOutcome, decisionDegraded) }}
            </Badge>
          </div>

          <p class="mt-3 text-lg font-semibold text-[color:var(--text-primary)]">
            {{ stateLabelResolved }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <span class="metric-pill">
            Этап: <span class="text-[color:var(--text-primary)]">{{ stageResolved }}</span>
          </span>
          <span class="metric-pill">
            Фаза: <span class="text-[color:var(--text-primary)]">{{ phaseResolved }}</span>
          </span>
          <span
            v-if="decisionReasonCode"
            class="metric-pill"
          >
            Decision:
            <span class="text-[color:var(--text-primary)]">
              {{ decisionReasonLabel(decisionReasonCode) || decisionReasonCode }}
            </span>
          </span>
          <span
            v-if="decisionStrategy"
            class="metric-pill"
          >
            Strategy: <span class="text-[color:var(--text-primary)]">{{ decisionStrategy }}</span>
          </span>
          <span
            v-if="decisionBundleRevision"
            class="metric-pill"
          >
            Bundle: <span class="text-[color:var(--text-primary)]">{{ shortRevision(decisionBundleRevision) }}</span>
          </span>
        </div>
      </div>

      <div
        v-if="activeProcessLabels.length > 0"
        class="mt-4 flex flex-wrap gap-2"
      >
        <Badge
          v-for="label in activeProcessLabels"
          :key="label"
          variant="info"
        >
          {{ label }}
        </Badge>
      </div>

      <p
        v-else
        class="mt-4 text-xs text-[color:var(--text-muted)]"
      >
        Активные подпроцессы не зафиксированы.
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'

type ActiveRunLike = {
  status?: string | null
  task_type?: string | null
  current_stage?: string | null
  workflow_phase?: string | null
}

type AutomationStateLike = {
  state_label?: string | null
  current_stage?: string | null
  workflow_phase?: string | null
  control_mode?: string | null
  decision?: {
    outcome?: string | null
    degraded?: boolean | null
    reason_code?: string | null
    strategy?: string | null
    bundle_revision?: string | null
  } | null
}

const props = defineProps<{
  updatedAt: string | null
  formatDateTime: (value: string | null) => string

  activeRun: ActiveRunLike | null
  automationState: AutomationStateLike | null
  workspaceControlMode: string | null | undefined

  activeProcessLabels: string[]

  statusVariant: (status: string) => any
  controlModeLabel: (mode: string | null | undefined) => string
  laneLabel: (taskType: string | null | undefined) => string

  decisionVariant: (outcome: string | null | undefined, degraded: boolean | null | undefined) => any
  decisionLabel: (outcome: string | null | undefined, degraded: boolean | null | undefined) => string
  decisionReasonLabel: (reason: string | null | undefined) => string | null
}>()

const controlModeResolved = computed(() => props.automationState?.control_mode || props.workspaceControlMode)
const decisionOutcome = computed(() => props.automationState?.decision?.outcome || null)
const decisionDegraded = computed(() => props.automationState?.decision?.degraded || null)
const decisionReasonCode = computed(() => props.automationState?.decision?.reason_code || null)
const decisionStrategy = computed(() => props.automationState?.decision?.strategy || null)
const decisionBundleRevision = computed(() => props.automationState?.decision?.bundle_revision || null)

const stageResolved = computed(() => props.automationState?.current_stage || props.activeRun?.current_stage || 'не передан')
const phaseResolved = computed(() => props.automationState?.workflow_phase || props.activeRun?.workflow_phase || 'не передана')
const stateLabelResolved = computed(() => {
  return (
    props.automationState?.state_label ||
    (props.activeRun ? props.laneLabel(props.activeRun.task_type) : 'Ожидание следующего запуска')
  )
})

const statusDotColor = computed(() => {
  const status = String(props.activeRun?.status ?? '').trim().toUpperCase()
  if (!props.activeRun) return 'text-[color:var(--text-dim)]'
  if (status.includes('FAIL') || status.includes('ERROR')) return 'text-[color:var(--accent-red)]'
  if (status.includes('COMPLETE') || status.includes('DONE') || status.includes('SUCCESS')) return 'text-[color:var(--accent-green)]'
  if (status.includes('RUN') || status.includes('ACTIVE') || status.includes('START')) return 'text-[color:var(--accent-cyan)]'
  if (status.includes('SKIP') || status.includes('SUPPRESS')) return 'text-[color:var(--text-dim)]'
  return 'text-[color:var(--text-muted)]'
})

function shortRevision(value: string | null | undefined): string {
  const normalized = String(value ?? '').trim()
  if (normalized === '') return '—'
  return normalized.slice(0, 12)
}
</script>
