<template>
  <section
    class="recent-runs-card rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3.5"
    data-testid="scheduler-recent-runs"
  >
    <header class="mb-2 flex items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <h4 class="m-0 text-[12px] font-semibold text-[color:var(--text-primary)]">
          Недавние исполнения
        </h4>
        <Badge
          variant="neutral"
          size="xs"
        >
          клик → цепочка решений
        </Badge>
      </div>
    </header>

    <div class="overflow-x-auto">
      <div
        class="grid min-w-[650px] rounded-t-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-main)]/20 px-2 py-1.5 text-[10px] uppercase tracking-[0.08em] text-[color:var(--text-muted)]"
        :style="gridStyle"
      >
        <span>ID</span>
        <span>Lane</span>
        <span>Decision</span>
        <span>cw · шагов</span>
        <span>Δ</span>
        <span class="sr-only">Выбор</span>
      </div>

      <div
        v-if="runs.length === 0"
        class="rounded-b-xl border border-t-0 border-[color:var(--border-muted)] px-2 py-3 text-[11px] text-[color:var(--text-muted)]"
      >
        Пока нет исполнений.
      </div>

      <button
        v-for="run in runs"
        :key="run.execution_id"
        type="button"
        class="row-hover grid min-w-[650px] w-full items-center gap-0 border-0 bg-transparent px-2 py-2 text-left text-[color:var(--text-primary)] transition-colors"
        :class="run.execution_id === selectedId ? 'bg-[color:var(--accent-cyan)]/10' : ''"
        :style="{
          ...gridStyle,
          borderLeft: `3px solid ${railColor(run)}`,
        }"
        :data-testid="`scheduler-runs-row-${run.execution_id}`"
        :data-selected="run.execution_id === selectedId"
        @click="$emit('select', run.execution_id)"
      >
        <span class="font-mono text-[11px] font-semibold">#{{ run.execution_id }}</span>
        <span class="truncate text-[11px] text-[color:var(--text-dim)]">
          {{ laneLabel(run.schedule_task_type ?? run.task_type) }}
        </span>
        <span class="truncate text-[11px] font-medium">
          {{ decisionLabel(run) }}
        </span>
        <span class="truncate font-mono text-[10px] text-[color:var(--text-muted)]">
          {{ chainSummary(run) }}
        </span>
        <span class="font-mono tabular-nums text-[11px] text-[color:var(--text-dim)]">
          {{ durationLabel(run) }}
        </span>
        <span
          class="text-[12px]"
          :class="run.execution_id === selectedId ? 'text-[color:var(--accent-cyan)]' : 'text-[color:var(--text-muted)]'"
        >{{ run.execution_id === selectedId ? '◉' : '→' }}</span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

interface Props {
  runs: ExecutionRun[]
  selectedId?: string | null
  laneLabel?: (taskType: string | null | undefined) => string
  decisionLabel?: (run: ExecutionRun) => string
  formatDuration?: (run: ExecutionRun) => string
}

const props = withDefaults(defineProps<Props>(), {
  selectedId: null,
  laneLabel: (value: string | null | undefined) => value ?? '—',
  decisionLabel: (run: ExecutionRun) => {
    const outcome = String(run.decision_outcome ?? run.status ?? '').toUpperCase()
    const reason = run.decision_reason_code ? ` · ${run.decision_reason_code}` : ''
    return outcome ? `${outcome}${reason}` : 'UNKNOWN'
  },
  formatDuration: undefined,
})

defineEmits<{
  select: [executionId: string]
}>()

const gridStyle = computed(() => ({
  gridTemplateColumns: '80px 120px minmax(0, 1fr) 140px 60px 20px',
}))

function railColor(run: ExecutionRun): string {
  const status = String(run.status ?? '').toLowerCase()
  if (run.is_active || status === 'running') return 'var(--accent-cyan)'
  if (status === 'failed' || status === 'fail' || status === 'error') return 'var(--accent-red)'
  if (status === 'completed' || status === 'complete' || status === 'done') return 'var(--accent-green)'
  if (status === 'skipped' || status === 'skip') return 'var(--text-dim)'
  return 'var(--border-muted)'
}

function chainSummary(run: ExecutionRun): string {
  const cw = run.correlation_id ?? '—'
  const length = run.timeline?.length ?? run.timeline_preview?.length ?? 0
  return length > 0 ? `${cw} · ${length} шагов` : cw
}

function durationLabel(run: ExecutionRun): string {
  if (props.formatDuration) return props.formatDuration(run)
  const start = run.accepted_at ?? run.created_at
  const end = run.completed_at ?? run.updated_at
  if (!start || !end) return '—'
  const diffMs = new Date(end).getTime() - new Date(start).getTime()
  if (!Number.isFinite(diffMs) || diffMs < 0) return '—'
  const total = Math.round(diffMs / 1000)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
</script>

<style scoped>
.recent-runs-card {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.row-hover:hover {
  background: color-mix(in srgb, var(--text-dim) 10%, transparent);
}
</style>
