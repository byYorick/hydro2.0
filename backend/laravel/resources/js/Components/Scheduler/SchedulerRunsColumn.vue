<template>
  <section class="surface-card rounded-xl border border-[color:var(--border-muted)] p-2 md:p-3">
    <div class="flex items-center justify-between gap-2">
      <h4 class="text-xs font-semibold text-[color:var(--text-primary)]">Исполнения</h4>
      <span class="text-[10px] text-[color:var(--text-muted)]">runtime: {{ runtime ?? '—' }}</span>
    </div>

    <!-- Активный run -->
    <div
      v-if="activeRun"
      class="mt-2 rounded-lg border border-[color:var(--accent-cyan)]/25 bg-[color:var(--accent-cyan)]/5 px-2.5 py-2"
    >
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="relative flex h-1.5 w-1.5 shrink-0">
          <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-[color:var(--accent-cyan)] opacity-75"></span>
          <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-[color:var(--accent-cyan)]"></span>
        </span>
        <Badge :variant="statusVariant(activeRun.status)">{{ statusLabel(activeRun.status) }}</Badge>
        <span class="font-mono text-[11px] font-semibold text-[color:var(--text-primary)]">#{{ activeRun.execution_id }}</span>
        <span class="text-[11px] text-[color:var(--text-dim)]">{{ laneLabel(activeRun.task_type) }}</span>
        <span class="ml-auto text-[10px] text-[color:var(--text-muted)]">{{ stageLabel(activeRun.current_stage) }}</span>
      </div>
      <p v-if="activeRun.decision_outcome" class="mt-1 flex flex-wrap gap-1">
        <Badge :variant="decisionVariant(activeRun.decision_outcome, activeRun.decision_degraded)" size="sm">
          {{ decisionLabel(activeRun.decision_outcome, activeRun.decision_degraded) }}
        </Badge>
        <Badge v-if="activeRun.decision_reason_code" variant="secondary" size="sm">
          {{ activeRun.decision_reason_code }}
        </Badge>
      </p>
      <p v-if="activeRunDecisionSummary" class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">
        {{ activeRunDecisionSummary }}
      </p>
    </div>

    <!-- Split-view: список + inline detail -->
    <div
      class="mt-2 gap-2"
      :class="selectedExecution ? 'grid xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]' : ''"
    >
      <!-- Список runs -->
      <div>
        <div class="flex items-center justify-between gap-2 mb-1.5">
          <h5 class="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">История</h5>
          <span class="text-[10px] text-[color:var(--text-muted)]">{{ recentRuns.length }} записей</span>
        </div>

        <div
          v-if="recentRuns.length === 0"
          class="rounded-md border border-dashed border-[color:var(--border-muted)] px-2.5 py-2 text-[11px] text-[color:var(--text-dim)]"
        >
          Исполнения не зафиксированы.
        </div>

        <div v-else class="space-y-0.5">
          <button
            v-for="run in recentRuns"
            :key="run.execution_id"
            type="button"
            class="group relative flex w-full items-center gap-2 overflow-hidden rounded-lg border px-2.5 py-2 text-left transition-colors"
            :class="selectedExecution?.execution_id === run.execution_id
              ? 'border-[color:var(--border-strong)] bg-[color:var(--surface-card)]/55'
              : 'border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/15 hover:bg-[color:var(--surface-card)]/40'"
            @click="$emit('select-run', run.execution_id)"
          >
            <span class="absolute left-0 top-0 h-full w-0.5" :class="railClass(run.status)"></span>

            <div class="min-w-0 flex-1 pl-1">
              <div class="flex flex-wrap items-center gap-1">
                <span class="font-mono text-[11px] font-semibold text-[color:var(--text-primary)]">
                  #{{ run.execution_id }}
                </span>
                <Badge :variant="statusVariant(run.status)" size="sm">{{ statusLabel(run.status) }}</Badge>
                <Badge
                  v-if="run.decision_outcome"
                  :variant="decisionVariant(run.decision_outcome, run.decision_degraded)"
                  size="sm"
                >
                  {{ decisionLabel(run.decision_outcome, run.decision_degraded) }}
                </Badge>
              </div>
              <p class="mt-0.5 truncate text-[10px] text-[color:var(--text-dim)]">
                {{ laneLabel(run.task_type) }} · {{ formatDateTime(run.updated_at ?? run.created_at ?? null) }}
              </p>
              <p v-if="decisionSummary(run)" class="mt-0.5 truncate text-[10px] text-[color:var(--text-muted)]">
                {{ decisionSummary(run) }}
              </p>
            </div>

            <span class="shrink-0 text-[11px] text-[color:var(--text-muted)]">
              {{ selectedExecution?.execution_id === run.execution_id ? '›' : stageLabel(run.current_stage) }}
            </span>
          </button>
        </div>
      </div>

      <!-- Inline Detail -->
      <Transition
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="opacity-0 translate-x-2"
        enter-to-class="opacity-100 translate-x-0"
        leave-active-class="transition-all duration-150 ease-in"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-2"
      >
        <div
          v-if="selectedExecution || detailLoading"
          class="overflow-hidden rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20"
        >
          <div v-if="detailLoading" class="px-3 py-5 text-xs text-[color:var(--text-dim)]">
            Загружаем детали...
          </div>

          <div v-else-if="selectedExecution" class="p-2.5 space-y-2">
            <!-- Заголовок detail -->
            <div class="flex items-center justify-between gap-2">
              <div class="flex flex-wrap items-center gap-1">
                <span class="font-mono text-[11px] font-semibold text-[color:var(--text-primary)]">
                  #{{ selectedExecution.execution_id }}
                </span>
                <Badge :variant="statusVariant(selectedExecution.status)" size="sm">
                  {{ statusLabel(selectedExecution.status) }}
                </Badge>
                <Badge
                  v-if="selectedExecution.decision_outcome"
                  :variant="decisionVariant(selectedExecution.decision_outcome, selectedExecution.decision_degraded)"
                  size="sm"
                >
                  {{ decisionLabel(selectedExecution.decision_outcome, selectedExecution.decision_degraded) }}
                </Badge>
              </div>
              <button
                type="button"
                class="text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors text-xs"
                @click="$emit('close-detail')"
              >
                ✕
              </button>
            </div>

            <!-- Метаданные -->
            <div class="flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-[color:var(--text-dim)]">
              <span>{{ laneLabel(selectedExecution.task_type) }}</span>
              <span>·</span>
              <span>{{ stageLabel(selectedExecution.current_stage) }}</span>
              <span v-if="selectedExecution.workflow_phase">· {{ selectedExecution.workflow_phase }}</span>
              <span v-if="selectedExecution.decision_strategy">· стратегия: {{ selectedExecution.decision_strategy }}</span>
            </div>
            <div class="flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-[color:var(--text-muted)]">
              <span>обновлено {{ formatDateTime(selectedExecution.updated_at ?? selectedExecution.created_at ?? null) }}</span>
              <span v-if="selectedExecution.scheduled_for">· план {{ formatDateTime(selectedExecution.scheduled_for) }}</span>
            </div>

            <!-- Ошибка -->
            <div
              v-if="selectedExecutionErrorMessage"
              class="rounded-md border border-red-300/50 bg-red-50/40 px-2.5 py-1.5 text-[11px] text-red-700 dark:border-red-800/40 dark:bg-red-950/20 dark:text-red-400"
            >
              {{ selectedExecutionErrorMessage }}
            </div>

            <!-- Decision summary -->
            <p v-if="selectedExecutionDecisionSummary" class="text-[10px] text-[color:var(--text-dim)]">
              {{ selectedExecutionDecisionSummary }}
            </p>

            <!-- Жизненный цикл -->
            <div
              v-if="selectedExecution.lifecycle && selectedExecution.lifecycle.length > 0"
              class="rounded-md border border-[color:var(--border-muted)] p-2"
            >
              <h5 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
                Жизненный цикл
              </h5>
              <div class="space-y-1">
                <div
                  v-for="(item, i) in selectedExecution.lifecycle"
                  :key="`lc-${i}`"
                  class="flex items-center justify-between gap-2 text-[11px]"
                >
                  <div class="flex items-center gap-1">
                    <Badge :variant="statusVariant(item.status)" size="sm">{{ statusLabel(item.status) }}</Badge>
                    <span class="text-[color:var(--text-dim)]">{{ item.source ?? 'runtime' }}</span>
                  </div>
                  <span class="text-[10px] text-[color:var(--text-muted)]">{{ formatDateTime(item.at) }}</span>
                </div>
              </div>
            </div>

            <!-- Хронология -->
            <div class="rounded-md border border-[color:var(--border-muted)] p-2">
              <h5 class="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
                Хронология
              </h5>
              <div v-if="condensedTimeline.length === 0" class="text-[11px] text-[color:var(--text-dim)]">
                Пусто.
              </div>
              <div v-else class="space-y-1">
                <div
                  v-for="(item, index) in condensedTimeline"
                  :key="item.key"
                  class="relative flex gap-1.5"
                >
                  <div class="relative flex w-3 shrink-0 flex-col items-center">
                    <span class="mt-1 h-1.5 w-1.5 rounded-full" :class="timelineDotClass(item)"></span>
                    <span
                      v-if="index < condensedTimeline.length - 1"
                      class="mt-0.5 flex-1 w-px bg-[color:var(--border-muted)]"
                    ></span>
                  </div>
                  <div class="min-w-0 flex-1 pb-1">
                    <div class="flex flex-wrap items-baseline gap-1">
                      <Badge variant="secondary" size="sm">{{ eventTypeLabel(item.event_type) }}</Badge>
                      <span class="text-[11px] font-medium text-[color:var(--text-primary)]">{{ item.label }}</span>
                      <span v-if="item.grouped" class="text-[9px] text-[color:var(--text-muted)]">группа</span>
                    </div>
                    <p v-if="item.detail" class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">{{ item.detail }}</p>
                    <p class="mt-0.5 text-[9px] text-[color:var(--text-muted)]">{{ formatDateTime(item.at) }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
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

type ExecutionDetail = RunLike & {
  irrigation_mode?: string | null
  decision_strategy?: string | null
  decision_config?: Record<string, unknown> | null
  decision_bundle_revision?: string | null
  lifecycle?: LifecycleItem[] | null
}

defineProps<{
  runtime: string | null | undefined
  activeRun: RunLike | null
  activeRunDecisionSummary: string | null
  recentRuns: RunLike[]
  selectedExecution: ExecutionDetail | null
  detailLoading: boolean
  condensedTimeline: TimelineItem[]
  selectedExecutionErrorMessage: string | null
  selectedExecutionDecisionSummary: string | null

  laneLabel: (taskType: string | null | undefined) => string
  stageLabel: (stage: string | null | undefined) => string
  statusVariant: (status: string) => any
  statusLabel: (status: string | null | undefined) => string
  eventTypeLabel: (eventType: string | null | undefined) => string
  decisionVariant: (outcome: string | null | undefined, degraded: boolean | null | undefined) => any
  decisionLabel: (outcome: string | null | undefined, degraded: boolean | null | undefined) => string
  formatDateTime: (value: string | null) => string
  decisionSummary: (run: RunLike | null | undefined) => string | null
}>()

defineEmits<{
  'select-run': [executionId: string]
  'close-detail': []
}>()

function railClass(status: string): string {
  const s = String(status ?? '').toUpperCase()
  if (s.includes('FAIL') || s.includes('ERROR')) return 'bg-[color:var(--accent-red)]'
  if (s.includes('COMPLETE') || s.includes('DONE')) return 'bg-[color:var(--accent-green)]'
  if (s.includes('RUN') || s.includes('ACTIVE') || s.includes('START')) return 'bg-[color:var(--accent-cyan)]'
  if (s.includes('SKIP') || s.includes('SUPPRESS')) return 'bg-[color:var(--text-dim)]'
  return 'bg-[color:var(--text-muted)]'
}

function timelineDotClass(item: TimelineItem): string {
  const t = String(item.event_type ?? '').toUpperCase()
  const l = String(item.label ?? '').toLowerCase()
  if (t.includes('FAILED') || t.includes('ERROR')) return 'bg-[color:var(--accent-red)]'
  if (t.includes('SKIP') || t.includes('SUPPRESS')) return 'bg-[color:var(--text-dim)]'
  if (t.includes('DEGRADED') || l.includes('деградир')) return 'bg-[color:var(--accent-amber)]'
  if (t.includes('COMPLETED') || t.includes('DONE')) return 'bg-[color:var(--accent-green)]'
  if (t.includes('START') || t.includes('RUN')) return 'bg-[color:var(--accent-cyan)]'
  return 'bg-[color:var(--text-muted)]'
}
</script>
