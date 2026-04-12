<template>
  <div
    class="flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-xl border px-3 py-2 transition-colors"
    :class="stripClass"
  >
    <!-- Живой индикатор -->
    <span class="relative flex h-1.5 w-1.5 shrink-0">
      <span
        v-if="isRunning"
        class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
        :class="pingColor"
      ></span>
      <span class="relative inline-flex h-1.5 w-1.5 rounded-full" :class="dotColor"></span>
    </span>

    <!-- Основной статус -->
    <span class="font-semibold text-xs text-[color:var(--text-primary)]">
      {{ stateLabelResolved }}
    </span>

    <span class="text-[color:var(--border-strong)]">·</span>

    <span class="text-xs text-[color:var(--text-dim)]">{{ stageResolved }}</span>

    <span class="text-[color:var(--border-strong)]">·</span>

    <span class="text-xs text-[color:var(--text-dim)]">{{ phaseResolved }}</span>

    <!-- Decision badge -->
    <Badge
      v-if="decisionOutcome"
      :variant="decisionVariant(decisionOutcome, decisionDegraded)"
      size="sm"
    >
      {{ decisionLabel(decisionOutcome, decisionDegraded) }}
    </Badge>

    <!-- Активные процессы -->
    <div class="ml-auto flex flex-wrap items-center gap-1">
      <Badge
        v-for="label in activeProcessLabels"
        :key="label"
        variant="info"
        size="sm"
      >
        {{ label }}
      </Badge>
      <span
        v-if="!activeProcessLabels.length"
        class="text-[11px] text-[color:var(--text-muted)]"
      >
        Ожидание
      </span>
    </div>

    <!-- Sync time -->
    <span class="text-[10px] text-[color:var(--text-muted)] hidden sm:inline">
      {{ updatedAt ? formatDateTime(updatedAt) : '' }}
    </span>
  </div>
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
  } | null
}

const props = defineProps<{
  updatedAt: string | null
  formatDateTime: (value: string | null) => string

  activeRun: ActiveRunLike | null
  automationState: AutomationStateLike | null

  activeProcessLabels: string[]

  laneLabel: (taskType: string | null | undefined) => string
  decisionVariant: (outcome: string | null | undefined, degraded: boolean | null | undefined) => any
  decisionLabel: (outcome: string | null | undefined, degraded: boolean | null | undefined) => string
}>()

const decisionOutcome = computed(() => props.automationState?.decision?.outcome ?? null)
const decisionDegraded = computed(() => props.automationState?.decision?.degraded ?? null)

const stageResolved = computed(
  () => props.automationState?.current_stage ?? props.activeRun?.current_stage ?? '—',
)
const phaseResolved = computed(
  () => props.automationState?.workflow_phase ?? props.activeRun?.workflow_phase ?? '—',
)
const stateLabelResolved = computed(
  () =>
    props.automationState?.state_label ??
    (props.activeRun ? props.laneLabel(props.activeRun.task_type) : 'Ожидание'),
)

const isRunning = computed(() => {
  const s = String(props.activeRun?.status ?? '').toUpperCase()
  return s.includes('RUN') || s.includes('ACTIVE') || s.includes('START')
})

const isFailed = computed(() => {
  const s = String(props.activeRun?.status ?? '').toUpperCase()
  return s.includes('FAIL') || s.includes('ERROR')
})

const dotColor = computed(() => {
  if (!props.activeRun) return 'bg-[color:var(--text-muted)]'
  if (isFailed.value) return 'bg-[color:var(--accent-red)]'
  if (isRunning.value) return 'bg-[color:var(--accent-cyan)]'
  const s = String(props.activeRun.status ?? '').toUpperCase()
  if (s.includes('COMPLETE') || s.includes('DONE')) return 'bg-[color:var(--accent-green)]'
  return 'bg-[color:var(--text-dim)]'
})

const pingColor = computed(() => {
  if (isFailed.value) return 'bg-[color:var(--accent-red)]'
  return 'bg-[color:var(--accent-cyan)]'
})

const stripClass = computed(() => {
  if (isFailed.value) return 'border-[color:var(--accent-red)]/30 bg-[color:var(--accent-red)]/5'
  if (isRunning.value) return 'border-[color:var(--accent-cyan)]/25 bg-[color:var(--accent-cyan)]/5'
  return 'border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20'
})
</script>
