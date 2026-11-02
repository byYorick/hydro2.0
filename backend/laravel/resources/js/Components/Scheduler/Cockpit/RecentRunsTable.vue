<template>
  <section
    class="recent-runs-card rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3.5"
    data-testid="scheduler-recent-runs"
  >
    <header class="mb-2 flex items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <h4 class="m-0 text-[12px] font-semibold text-[color:var(--text-primary)]">
          История запусков
        </h4>
        <Badge
          variant="neutral"
          size="xs"
        >
          Выберите запуск, чтобы открыть детали
        </Badge>
      </div>
    </header>

    <div
      v-if="showFilters"
      class="mb-3 grid gap-2 sm:grid-cols-2"
    >
      <TextField
        v-model="query"
        type="search"
        aria-label="Поиск запусков"
        placeholder="Номер, задача или причина"
        data-testid="scheduler-history-search"
      />
      <SelectField
        v-model="statusFilter"
        aria-label="Статус запуска"
        data-testid="scheduler-history-status"
      >
        <option value="all">
          Все статусы
        </option><option value="active">
          В работе
        </option><option value="failed">
          С ошибкой
        </option><option value="completed">
          Завершены
        </option>
      </SelectField>
    </div>

    <div class="overflow-x-auto">
      <div
        class="grid min-w-[650px] rounded-t-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-main)]/20 px-2 py-1.5 text-[10px] uppercase tracking-[0.08em] text-[color:var(--text-muted)]"
        :style="gridStyle"
      >
        <span>ID</span>
        <span>Задача</span>
        <span>Решение</span>
        <span>Статус</span>
        <span>Время</span>
        <span class="sr-only">Выбор</span>
      </div>

      <div
        v-if="visibleRuns.length === 0"
        class="rounded-b-xl border border-t-0 border-[color:var(--border-muted)] px-2 py-3 text-[11px] text-[color:var(--text-muted)]"
      >
        {{ runs.length ? 'По выбранным условиям запусков нет.' : 'Пока нет исполнений.' }}
      </div>

      <button
        v-for="run in visibleRuns"
        :key="run.execution_id"
        type="button"
        class="row-hover grid min-w-[650px] w-full items-center gap-0 border-0 bg-transparent px-2 py-2 text-left text-[color:var(--text-primary)] transition-colors"
        :class="run.execution_id === selectedId ? 'bg-[color:var(--status-info)]/10' : ''"
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
        <span class="min-w-0 text-[11px] font-medium">
          <span class="block truncate">{{ decisionLabel(run) }}</span>
          <span
            v-if="chemistryLabel(run)"
            class="mt-0.5 block truncate text-[10px]"
            :class="chemistryClass(run)"
            :data-testid="`scheduler-runs-chemistry-${run.execution_id}`"
          >{{ chemistryLabel(run) }}</span>
        </span>
        <span class="truncate font-mono text-[10px] text-[color:var(--text-muted)]">
          {{ statusLabel(run.status) }}
        </span>
        <span class="font-mono tabular-nums text-[11px] text-[color:var(--text-dim)]">
          {{ durationLabel(run) }}
        </span>
        <span
          class="text-[12px]"
          :class="run.execution_id === selectedId ? 'text-[color:var(--status-info)]' : 'text-[color:var(--text-muted)]'"
        >{{ run.execution_id === selectedId ? '◉' : '→' }}</span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import TextField from '@/Components/TextField.vue'
import SelectField from '@/Components/SelectField.vue'
import { statusLabel } from '@/utils/schedulerLabels'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

interface Props {
  runs: ExecutionRun[]
  selectedId?: string | null
  laneLabel?: (taskType: string | null | undefined) => string
  decisionLabel?: (run: ExecutionRun) => string
  formatDuration?: (run: ExecutionRun) => string
  showFilters?: boolean
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
  showFilters: false,
})

const emit = defineEmits<{
  select: [executionId: string]
  'visible-runs': [runs: ExecutionRun[]]
}>()
const query = ref('')
const statusFilter = ref('all')
const visibleRuns = computed(() => props.runs.filter(run => {
  if (!props.showFilters) return true
  const status = String(run.status).toLowerCase()
  if (statusFilter.value === 'active' && !run.is_active) return false
  if (statusFilter.value === 'failed' && !['failed', 'fail', 'error'].includes(status)) return false
  if (statusFilter.value === 'completed' && !['completed', 'complete', 'done'].includes(status)) return false
  const term = query.value.trim().toLocaleLowerCase('ru')
  return !term || [run.execution_id, props.laneLabel(run.schedule_task_type ?? run.task_type), props.decisionLabel(run), run.error_code, run.human_error_message].some(value => String(value ?? '').toLocaleLowerCase('ru').includes(term))
}))
watch(visibleRuns, runs => emit('visible-runs', runs), { immediate: true })

const gridStyle = computed(() => ({
  gridTemplateColumns: '80px 120px minmax(0, 1fr) 140px 60px 20px',
}))

function railColor(run: ExecutionRun): string {
  const status = String(run.status ?? '').toLowerCase()
  if (run.is_active || status === 'running') return 'var(--status-info)'
  if (status === 'failed' || status === 'fail' || status === 'error') return 'var(--status-critical)'
  if (run.chemistry_outcome === 'targets_not_achieved' || run.chemistry_outcome === 'unknown') return 'var(--status-warning)'
  if (status === 'completed' || status === 'complete' || status === 'done') return 'var(--status-ok)'
  if (status === 'skipped' || status === 'skip') return 'var(--text-dim)'
  return 'var(--border-muted)'
}

function chemistryLabel(run: ExecutionRun): string {
  if (run.chemistry_outcome === 'targets_achieved') return 'Химия: цели достигнуты'
  if (run.chemistry_outcome === 'targets_not_achieved') return 'Химия: цели не достигнуты'
  if (run.chemistry_outcome === 'unknown') return 'Химия: результат не подтверждён'
  if (run.chemistry_outcome === 'failed') return 'Химия: ошибка коррекции'
  return ''
}

function chemistryClass(run: ExecutionRun): string {
  return run.chemistry_outcome === 'targets_achieved'
    ? 'text-status-ok'
    : 'text-status-warning'
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
