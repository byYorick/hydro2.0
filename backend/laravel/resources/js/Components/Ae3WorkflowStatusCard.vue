<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3">
    <!-- Loading skeleton -->
    <div
      v-if="loading && !activeTask"
      class="space-y-3 animate-pulse"
    >
      <div class="flex items-center justify-between">
        <div class="space-y-1.5">
          <div class="h-2.5 w-24 rounded bg-[color:var(--surface-muted)]" />
          <div class="h-5 w-32 rounded bg-[color:var(--surface-muted)]" />
        </div>
      </div>
      <div class="flex items-center gap-1 flex-wrap">
        <div
          v-for="i in 5"
          :key="i"
          class="h-5 w-16 rounded-full bg-[color:var(--surface-muted)]"
        />
      </div>
    </div>

    <template v-else>
      <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div class="space-y-1 min-w-0">
          <p class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">AE3-Lite workflow</p>
          <div class="flex flex-wrap items-center gap-2">
            <Badge :variant="phaseBadgeVariant">{{ currentPhaseLabel }}</Badge>
            <span
              v-if="activeTask"
              class="text-xs text-[color:var(--text-muted)]"
            >
              задача #{{ activeTask.task_id }}
            </span>
          </div>
        </div>
        <Badge
          v-if="isRunning"
          variant="info"
        >
          Выполняется
        </Badge>
      </div>

      <!-- Workflow phase steps -->
      <div class="flex items-center gap-1 flex-wrap">
        <template
          v-for="(step, idx) in WORKFLOW_PHASES"
          :key="step.phase"
        >
          <div
            class="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full transition-colors"
            :class="getPhaseClass(step.phase)"
          >
            {{ step.label }}
          </div>
          <span
            v-if="idx < WORKFLOW_PHASES.length - 1"
            class="text-[color:var(--text-dim)] text-xs"
          >→</span>
        </template>
      </div>

      <!-- Current task process steps -->
      <div
        v-if="activeTask?.process_steps?.length"
        class="space-y-1 pt-1 border-t border-[color:var(--border-muted)]"
      >
        <p class="text-[10px] uppercase tracking-widest text-[color:var(--text-dim)]">Шаги задачи</p>
        <div class="space-y-1">
          <div
            v-for="step in activeTask.process_steps"
            :key="step.phase"
            class="flex items-center gap-2 text-xs"
          >
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :class="getStepDotClass(step.status)"
            />
            <span class="text-[color:var(--text-muted)] min-w-[120px]">{{ step.label }}</span>
            <Badge
              :variant="getStepVariant(step.status)"
              class="text-[10px]"
            >
              {{ step.status_label || step.status }}
            </Badge>
            <span
              v-if="step.last_reason_code"
              class="text-[color:var(--text-dim)] truncate"
            >{{ step.last_reason_code }}</span>
          </div>
        </div>
      </div>

      <!-- No active task -->
      <div
        v-if="!activeTask"
        class="text-sm text-[color:var(--text-dim)] text-center py-2"
      >
        Нет активных AE3 задач
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { SchedulerTaskStatus } from '@/composables/zoneAutomationTypes'

interface Props {
  recentSchedulerTasks: SchedulerTaskStatus[]
  loading?: boolean
}

const props = defineProps<Props>()

// AE3-Lite workflow phases in order
const WORKFLOW_PHASES = [
  { phase: 'startup', label: 'Запуск' },
  { phase: 'clean_fill', label: 'Заполнение' },
  { phase: 'solution_fill', label: 'Раствор' },
  { phase: 'prepare_recirc', label: 'Рециркуляция' },
  { phase: 'ready', label: 'Готово' },
  { phase: 'irrig_recirc', label: 'Полив' },
] as const

type WorkflowPhase = (typeof WORKFLOW_PHASES)[number]['phase']

// Find the most relevant active or recent task
const activeTask = computed<SchedulerTaskStatus | null>(() => {
  const tasks = props.recentSchedulerTasks
  // Prefer running/accepted task first
  const running = tasks.find((t) => t.status === 'running' || t.status === 'accepted')
  if (running) return running
  // Fall back to the most recent task
  return tasks[0] ?? null
})

const isRunning = computed(() =>
  activeTask.value?.status === 'running' || activeTask.value?.status === 'accepted'
)

// Extract current workflow phase from process_state or process_steps
const currentPhase = computed<string | null>(() => {
  const task = activeTask.value
  if (!task) return null
  // process_state.phase is the most direct source
  const phase = task.process_state?.phase
  if (phase) return phase
  // Fall back to the running process_step phase
  const runningStep = task.process_steps?.find((s) => s.status === 'running' || s.status === 'in_progress')
  if (runningStep) return runningStep.phase
  // The last completed step
  const completedSteps = task.process_steps?.filter((s) => s.status === 'completed' || s.status === 'done') ?? []
  if (completedSteps.length) return completedSteps[completedSteps.length - 1].phase
  return null
})

const phaseLabels: Record<WorkflowPhase, string> = {
  startup: 'Запуск',
  clean_fill: 'Заполнение чистой воды',
  solution_fill: 'Заполнение раствора',
  prepare_recirc: 'Подготовка рециркуляции',
  ready: 'Готово',
  irrig_recirc: 'Полив (рециркуляция)',
}

const currentPhaseLabel = computed(() => {
  if (!activeTask.value) return 'Нет данных'
  const phase = currentPhase.value as WorkflowPhase | null
  if (phase && phase in phaseLabels) return phaseLabels[phase]
  const statusLabel = activeTask.value.process_state?.phase_label
  if (statusLabel) return statusLabel
  return activeTask.value.status ?? 'Нет данных'
})

const phaseBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'success'>(() => {
  if (!activeTask.value) return 'neutral'
  const phase = currentPhase.value
  if (phase === 'ready') return 'success'
  if (phase === 'irrig_recirc') return 'info'
  if (phase === 'prepare_recirc') return 'warning'
  if (isRunning.value) return 'info'
  const status = activeTask.value.status
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'neutral'
  return 'neutral'
})

function getPhaseClass(phase: string): string {
  const current = currentPhase.value
  if (phase === current) {
    return isRunning.value
      ? 'bg-[color:var(--accent,#3b82f6)]/20 text-[color:var(--accent,#3b82f6)] font-semibold'
      : 'bg-[color:var(--surface-muted)] text-[color:var(--text-primary)] font-medium'
  }
  // Check if this phase is already passed
  const phases = WORKFLOW_PHASES.map((p) => p.phase)
  const currentIdx = phases.indexOf(current as WorkflowPhase)
  const thisIdx = phases.indexOf(phase as WorkflowPhase)
  if (currentIdx !== -1 && thisIdx < currentIdx) {
    return 'bg-[color:var(--surface-muted)]/40 text-[color:var(--text-dim)] line-through'
  }
  return 'text-[color:var(--text-dim)]'
}

function getStepDotClass(status: string): string {
  const s = status?.toLowerCase()
  if (s === 'completed' || s === 'done') return 'bg-green-500'
  if (s === 'running' || s === 'in_progress') return 'bg-blue-500 animate-pulse'
  if (s === 'failed') return 'bg-red-500'
  return 'bg-[color:var(--text-dim)]'
}

function getStepVariant(status: string): 'neutral' | 'info' | 'warning' | 'success' | 'danger' {
  const s = status?.toLowerCase()
  if (s === 'completed' || s === 'done') return 'success'
  if (s === 'running' || s === 'in_progress') return 'info'
  if (s === 'failed') return 'danger'
  return 'neutral'
}
</script>
