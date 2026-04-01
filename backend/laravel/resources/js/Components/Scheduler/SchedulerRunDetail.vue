<template>
  <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Детали run</h4>
        <p class="text-sm text-[color:var(--text-dim)]">
          Сжатый timeline без мусорных повторов `AE_TASK_STARTED`.
        </p>
      </div>
      <Badge :variant="selectedExecution ? statusVariant(selectedExecution.status) : 'secondary'">
        {{ selectedExecution ? selectedExecution.status : '—' }}
      </Badge>
    </div>

    <div
      v-if="detailLoading"
      class="mt-4 text-sm text-[color:var(--text-dim)]"
    >
      Загружаем детали выполнения...
    </div>

    <div
      v-else-if="!selectedExecution"
      class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
    >
      Выберите run справа, чтобы посмотреть lifecycle и timeline.
    </div>

    <div
      v-else
      class="mt-4 space-y-4"
    >
      <div class="grid gap-3 md:grid-cols-2">
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
          <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Run</p>
          <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">#{{ selectedExecution.execution_id }}</p>
          <p class="mt-1 text-xs text-[color:var(--text-muted)]">
            {{ laneLabel(selectedExecution.task_type) }} · {{ selectedExecution.current_stage || 'stage не передан' }}
          </p>
          <div
            v-if="selectedExecution.decision_outcome"
            class="mt-2 flex flex-wrap gap-2"
          >
            <Badge :variant="decisionVariant(selectedExecution.decision_outcome, selectedExecution.decision_degraded)">
              {{ decisionLabel(selectedExecution.decision_outcome, selectedExecution.decision_degraded) }}
            </Badge>
            <Badge
              v-if="selectedExecution.decision_reason_code"
              variant="secondary"
            >
              {{ selectedExecution.decision_reason_code }}
            </Badge>
          </div>
          <p
            v-if="selectedExecutionDecisionSummary"
            class="mt-2 text-xs text-[color:var(--text-dim)]"
          >
            {{ selectedExecutionDecisionSummary }}
          </p>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
          <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Время</p>
          <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
            updated {{ formatDateTime(selectedExecution.updated_at || selectedExecution.created_at || null) }}
          </p>
          <p class="mt-1 text-xs text-[color:var(--text-muted)]">
            planned {{ formatDateTime(selectedExecution.scheduled_for || null) }}
          </p>
          <p
            v-if="selectedExecution.irrigation_mode || selectedExecution.decision_strategy"
            class="mt-1 text-xs text-[color:var(--text-dim)]"
          >
            {{ selectedExecution.irrigation_mode ? `mode ${selectedExecution.irrigation_mode}` : '' }}
            {{ selectedExecution.irrigation_mode && selectedExecution.decision_strategy ? ' · ' : '' }}
            {{ selectedExecution.decision_strategy ? `strategy ${selectedExecution.decision_strategy}` : '' }}
          </p>
        </div>
      </div>

      <div
        v-if="selectedExecutionErrorMessage"
        class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        {{ selectedExecutionErrorMessage }}
      </div>

      <div
        v-if="selectedExecution.lifecycle && selectedExecution.lifecycle.length > 0"
        class="rounded-xl border border-[color:var(--border-muted)] p-4"
      >
        <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Lifecycle</h5>
        <div class="mt-3 space-y-2">
          <div
            v-for="(item, index) in selectedExecution.lifecycle"
            :key="`${selectedExecution.execution_id}-lifecycle-${index}`"
            class="flex items-center justify-between gap-3 text-sm"
          >
            <div class="flex items-center gap-2">
              <Badge :variant="statusVariant(item.status)">{{ item.status }}</Badge>
              <span class="text-[color:var(--text-primary)]">{{ item.source || 'runtime' }}</span>
            </div>
            <span class="text-xs text-[color:var(--text-muted)]">{{ formatDateTime(item.at) }}</span>
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
        <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Timeline</h5>
        <div
          v-if="condensedTimeline.length === 0"
          class="mt-3 text-sm text-[color:var(--text-dim)]"
        >
          Timeline для этого run пока пустой.
        </div>
        <div
          v-else
          class="mt-3 space-y-2"
        >
          <div
            v-for="(item, index) in condensedTimeline"
            :key="item.key"
            class="relative flex gap-3"
          >
            <div class="relative flex w-4 shrink-0 justify-center">
              <span
                class="mt-2 h-2.5 w-2.5 rounded-full"
                :class="timelineDotClass(item)"
              />
              <span
                v-if="index < condensedTimeline.length - 1"
                class="absolute bottom-0 top-4 w-px bg-[color:var(--border-muted)]"
              />
            </div>

            <div class="min-w-0 flex-1 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3">
              <div class="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge variant="info">{{ item.event_type }}</Badge>
                    <span class="text-sm font-medium text-[color:var(--text-primary)]">
                      {{ item.label }}
                    </span>
                    <span
                      v-if="item.grouped"
                      class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]"
                    >
                      grouped
                    </span>
                  </div>
                  <p
                    v-if="item.detail"
                    class="mt-2 text-xs text-[color:var(--text-dim)]"
                  >
                    {{ item.detail }}
                  </p>
                </div>
                <span class="shrink-0 text-xs text-[color:var(--text-muted)]">
                  {{ formatDateTime(item.at) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'

type LifecycleItem = {
  status: string
  source?: string | null
  at: string
}

type TimelineItem = {
  key: string
  event_type: string
  label: string
  at: string
  grouped?: boolean
  detail?: string | null
}

type ExecutionDetail = {
  execution_id: string
  status: string
  task_type?: string | null
  current_stage?: string | null
  workflow_phase?: string | null
  scheduled_for?: string | null
  updated_at?: string | null
  created_at?: string | null
  irrigation_mode?: string | null
  decision_strategy?: string | null
  decision_outcome?: string | null
  decision_degraded?: boolean | null
  decision_reason_code?: string | null
  lifecycle?: LifecycleItem[] | null
}

defineProps<{
  detailLoading: boolean
  selectedExecution: ExecutionDetail | null
  condensedTimeline: TimelineItem[]
  selectedExecutionErrorMessage: string | null
  selectedExecutionDecisionSummary: string | null

  laneLabel: (taskType: string | null | undefined) => string
  statusVariant: (status: string) => any
  decisionVariant: (outcome: string | null | undefined, degraded: boolean | null | undefined) => any
  decisionLabel: (outcome: string | null | undefined, degraded: boolean | null | undefined) => string
  formatDateTime: (value: string | null) => string
}>()

function timelineDotClass(item: TimelineItem): string {
  const normalizedType = String(item.event_type ?? '').trim().toUpperCase()
  const normalizedLabel = String(item.label ?? '').trim().toLowerCase()

  if (normalizedType.includes('FAILED') || normalizedType.includes('ERROR')) return 'bg-[color:var(--accent-red)]'
  if (normalizedType.includes('SKIP') || normalizedType.includes('SUPPRESS')) return 'bg-[color:var(--text-dim)]'
  if (normalizedType.includes('DEGRADED') || normalizedLabel.includes('degraded')) return 'bg-[color:var(--accent-amber)]'
  if (normalizedType.includes('COMPLETED') || normalizedType.includes('DONE')) return 'bg-[color:var(--accent-green)]'
  if (normalizedType.includes('START') || normalizedType.includes('RUN')) return 'bg-[color:var(--accent-cyan)]'

  return 'bg-[color:var(--text-muted)]'
}
</script>

