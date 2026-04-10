<template>
  <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
    <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">
          Исполнения
        </h4>
        <p class="text-sm text-[color:var(--text-dim)]">
          Активный run и недавняя история по каноническим `ae_tasks`.
        </p>
      </div>
      <div class="text-xs text-[color:var(--text-muted)]">
        Runtime: {{ runtime ?? '—' }}
      </div>
    </div>

    <div class="mt-4 grid gap-3">
      <div class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
        <div class="flex flex-wrap items-center gap-2">
          <Badge :variant="activeRun ? statusVariant(activeRun.status) : 'secondary'">
            {{ activeRun ? activeRun.status : 'idle' }}
          </Badge>
          <span class="text-sm font-semibold text-[color:var(--text-primary)]">
            {{ activeRun ? `#${activeRun.execution_id}` : 'Активного run нет' }}
          </span>
        </div>
        <p class="mt-2 text-sm text-[color:var(--text-dim)]">
          {{ activeRun ? `${laneLabel(activeRun.task_type)} · ${activeRun.current_stage || 'stage не передан'}` : 'Ожидание следующего wake-up.' }}
        </p>
        <div
          v-if="activeRun?.decision_outcome"
          class="mt-2 flex flex-wrap gap-2"
        >
          <Badge :variant="decisionVariant(activeRun.decision_outcome, activeRun.decision_degraded)">
            {{ decisionLabel(activeRun.decision_outcome, activeRun.decision_degraded) }}
          </Badge>
          <Badge
            v-if="activeRun.decision_reason_code"
            variant="secondary"
          >
            {{ activeRun.decision_reason_code }}
          </Badge>
        </div>
        <p
          v-if="activeRun?.scheduled_for"
          class="mt-1 text-xs text-[color:var(--text-muted)]"
        >
          planned: {{ formatDateTime(activeRun.scheduled_for) }}
        </p>
        <p
          v-if="activeRunDecisionSummary"
          class="mt-2 text-xs text-[color:var(--text-dim)]"
        >
          {{ activeRunDecisionSummary }}
        </p>
      </div>

      <div class="rounded-2xl border border-[color:var(--border-muted)] p-4">
        <div class="flex items-center justify-between gap-3">
          <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Недавние run
          </h5>
          <span class="text-xs text-[color:var(--text-muted)]">{{ recentRuns.length }} записей</span>
        </div>

        <div
          v-if="recentRuns.length === 0"
          class="mt-3 text-sm text-[color:var(--text-dim)]"
        >
          Исполнения ещё не зафиксированы.
        </div>

        <div
          v-else
          class="mt-3 space-y-2"
        >
          <button
            v-for="run in recentRuns"
            :key="run.execution_id"
            type="button"
            class="group relative flex w-full items-center justify-between gap-3 overflow-hidden rounded-xl border px-3 py-3 text-left transition-colors"
            :class="selectedExecutionId === run.execution_id
              ? 'border-[color:var(--border-strong)] bg-[color:var(--surface-card)]/55'
              : 'border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 hover:bg-[color:var(--surface-card)]/45'"
            @click="$emit('select-run', run.execution_id)"
          >
            <span
              class="absolute left-0 top-0 h-full w-1"
              :class="statusRailClass(run.status)"
            ></span>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">#{{ run.execution_id }}</span>
                <Badge :variant="statusVariant(run.status)">
                  {{ run.status }}
                </Badge>
                <Badge
                  v-if="run.decision_outcome"
                  :variant="decisionVariant(run.decision_outcome, run.decision_degraded)"
                >
                  {{ decisionLabel(run.decision_outcome, run.decision_degraded) }}
                </Badge>
                <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                  {{ laneLabel(run.task_type) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                {{ formatDateTime(run.updated_at || run.created_at || null) }}
              </p>
              <p
                v-if="decisionSummary(run)"
                class="mt-1 text-xs text-[color:var(--text-dim)]"
              >
                {{ decisionSummary(run) }}
              </p>
            </div>
            <span class="shrink-0 text-xs text-[color:var(--text-dim)]">
              {{ run.current_stage || run.workflow_phase || '—' }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'

type RunLike = {
  execution_id: string
  status: string
  task_type?: string | null
  current_stage?: string | null
  workflow_phase?: string | null
  scheduled_for?: string | null
  updated_at?: string | null
  created_at?: string | null
  decision_outcome?: string | null
  decision_degraded?: boolean | null
  decision_reason_code?: string | null
  error_code?: string | null
  replay_count?: number | null
}

defineProps<{
  runtime: string | null | undefined
  activeRun: RunLike | null
  activeRunDecisionSummary: string | null
  recentRuns: RunLike[]
  selectedExecutionId: string | null

  laneLabel: (taskType: string | null | undefined) => string
  statusVariant: (status: string) => any
  decisionVariant: (outcome: string | null | undefined, degraded: boolean | null | undefined) => any
  decisionLabel: (outcome: string | null | undefined, degraded: boolean | null | undefined) => string
  formatDateTime: (value: string | null) => string
  decisionSummary: (run: RunLike | null | undefined) => string | null
}>()

defineEmits<{
  'select-run': [executionId: string]
}>()

function statusRailClass(status: string): string {
  const normalized = String(status ?? '').trim().toUpperCase()
  if (normalized.includes('FAIL') || normalized.includes('ERROR')) return 'bg-[color:var(--accent-red)]'
  if (normalized.includes('COMPLETE') || normalized.includes('DONE') || normalized.includes('SUCCESS')) return 'bg-[color:var(--accent-green)]'
  if (normalized.includes('RUN') || normalized.includes('ACTIVE') || normalized.includes('START')) return 'bg-[color:var(--accent-cyan)]'
  if (normalized.includes('SKIP') || normalized.includes('SUPPRESS') || normalized.includes('IDLE')) return 'bg-[color:var(--text-dim)]'
  return 'bg-[color:var(--text-muted)]'
}
</script>

