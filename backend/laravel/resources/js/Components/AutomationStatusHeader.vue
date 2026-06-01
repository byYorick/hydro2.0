<template>
  <header class="automation-status-hero space-y-4">
    <div
      class="rounded-2xl border border-[color:var(--border-muted)]/70 bg-gradient-to-br from-[color:var(--surface-card)]/90 to-[color:var(--surface-muted)]/25 p-4 md:p-5"
    >
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0 space-y-2">
        <p class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">
          Текущий этап
        </p>
          <h3 class="text-lg font-semibold leading-snug text-[color:var(--text-primary)] md:text-xl">
            {{ stateLabel }}
          </h3>
          <p
            v-if="showMacroPhaseSubtitle"
            class="text-sm text-[color:var(--text-muted)]"
          >
            {{ macroPhaseLabel }}
          </p>
        </div>

        <div class="flex shrink-0 flex-col items-start gap-2 lg:items-end">
          <StatusIndicator
            :status="stateCode"
            :variant="stateVariant"
            :pulse="isProcessActive"
            :show-label="true"
          />
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <span
              v-if="displayElapsedLabel"
              class="inline-flex items-center rounded-full border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/70 px-2.5 py-1 font-mono text-xs tabular-nums text-[color:var(--text-primary)]"
            >
              {{ displayElapsedLabel }}
            </span>
            <span
              v-if="showProgressPercent && progressPercent > 0"
              class="text-xs text-[color:var(--text-muted)]"
            >
              {{ progressPercent }}%
            </span>
            <span
              v-else-if="progressSummary && progressSummary !== '—'"
              class="text-xs text-[color:var(--text-muted)]"
            >
              {{ progressSummary }}
            </span>
          </div>
        </div>
      </div>

      <div
        v-if="showProgressPercent"
        class="mt-4 space-y-1.5"
      >
        <div class="flex items-center justify-between text-[11px] uppercase tracking-[0.14em] text-[color:var(--text-dim)]">
          <span>Ход workflow</span>
          <span v-if="progressPercent > 0">{{ progressPercent }}%</span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-[color:var(--surface-muted)]/70">
          <div
            class="h-full rounded-full bg-amber-400/90 transition-all duration-500"
            :style="{ width: `${Math.max(progressPercent, isProcessActive ? 8 : 0)}%` }"
          />
        </div>
      </div>
    </div>

    <p
      v-if="errorMessage"
      class="text-xs text-red-500"
    >
      {{ errorMessage }}
    </p>
    <p
      v-if="warningMessage"
      class="text-xs text-amber-400"
    >
      {{ warningMessage }}
    </p>

    <section class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/40 p-3">
      <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
          Этапы
        </h4>
        <p class="text-xs text-[color:var(--text-muted)]">
          Сейчас: <span class="text-[color:var(--text-primary)]">{{ currentWorkflowStageLabel }}</span>
        </p>
      </div>
      <ul class="mt-3 flex min-w-max items-stretch gap-1 overflow-x-auto pb-1">
        <li
          v-for="(stage, index) in workflowStages"
          :key="stage.code"
          class="flex items-center"
        >
          <div
            class="flex min-w-[9.5rem] max-w-[11rem] flex-col justify-between rounded-lg border px-2.5 py-2 transition-colors"
            :class="stageCardClass(stage.status)"
          >
            <div class="flex items-start gap-2">
              <span
                class="pipeline-stage-dot shrink-0"
                :class="stageDotClass(stage.status)"
                :title="workflowStageStatusLabel(stage.status)"
              >
                {{ stageStatusIcon(stage.status) }}
              </span>
              <span class="line-clamp-2 text-[11px] leading-[1.15rem] text-[color:var(--text-primary)]">
                {{ stage.label }}
              </span>
            </div>
            <span
              class="mt-2 self-start rounded-full px-2 py-0.5 text-[10px] font-medium"
              :class="stagePillClass(stage.status)"
            >
              {{ workflowStageStatusLabel(stage.status) }}
            </span>
          </div>
          <span
            v-if="index < workflowStages.length - 1"
            class="pipeline-connector mx-0.5"
            :class="connectorClass(stage.status)"
            aria-hidden="true"
          />
        </li>
      </ul>
    </section>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusIndicator from '@/Components/StatusIndicator.vue'
import { formatAutomationDuration } from '@/utils/automationStatusDisplay'
import type { AutomationStateType, WorkflowStageStatus, WorkflowStageView } from '@/types/Automation'

type PipelineStageVisualStatus = WorkflowStageStatus | 'manual' | 'canceled' | 'skipped'

interface Props {
  stateCode: AutomationStateType
  stateLabel: string
  macroPhaseLabel: string
  showMacroPhaseSubtitle: boolean
  stateVariant: 'neutral' | 'info' | 'warning' | 'success' | 'danger'
  isProcessActive: boolean
  progressSummary: string
  displayElapsedSec: number
  progressPercent: number
  showProgressPercent: boolean
  errorMessage: string | null
  warningMessage: string | null
  workflowStages: WorkflowStageView[]
  currentWorkflowStageLabel: string
}

const props = defineProps<Props>()

const displayElapsedLabel = computed(() => formatAutomationDuration(props.displayElapsedSec))

function workflowStageStatusLabel(status: PipelineStageVisualStatus): string {
  if (status === 'running') return 'Сейчас'
  if (status === 'completed') return 'Готово'
  if (status === 'failed') return 'Ошибка'
  if (status === 'manual') return 'Ручной'
  if (status === 'canceled') return 'Отменено'
  if (status === 'skipped') return 'Пропуск'
  return 'Далее'
}

function stageStatusIcon(status: PipelineStageVisualStatus): string {
  if (status === 'completed') return '✓'
  if (status === 'failed') return '!'
  if (status === 'running') return '●'
  if (status === 'manual') return '▶'
  if (status === 'canceled') return '×'
  if (status === 'skipped') return '›'
  return '○'
}

function stageCardClass(status: PipelineStageVisualStatus): string {
  if (status === 'running') {
    return 'border-amber-400/45 bg-amber-500/10 shadow-[0_0_0_1px_rgb(245_158_11/0.15)]'
  }
  if (status === 'completed') {
    return 'border-emerald-400/35 bg-emerald-500/8'
  }
  if (status === 'failed') {
    return 'border-red-400/35 bg-red-500/10'
  }
  return 'border-[color:var(--border-muted)]/40 bg-[color:var(--surface-card)]/25'
}

function stagePillClass(status: PipelineStageVisualStatus): string {
  if (status === 'running') {
    return 'bg-amber-500/20 text-amber-300 border border-amber-400/40'
  }
  if (status === 'completed') {
    return 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/40'
  }
  if (status === 'failed') {
    return 'bg-red-500/20 text-red-300 border border-red-400/40'
  }
  if (status === 'manual') {
    return 'bg-sky-500/20 text-sky-300 border border-sky-400/40'
  }
  if (status === 'canceled') {
    return 'bg-zinc-500/25 text-zinc-300 border border-zinc-400/40'
  }
  if (status === 'skipped') {
    return 'bg-slate-500/20 text-slate-300 border border-slate-400/40'
  }
  return 'bg-slate-500/15 text-slate-400 border border-slate-500/30'
}

function stageDotClass(status: PipelineStageVisualStatus): string {
  if (status === 'running') return 'pipeline-stage-dot--running'
  if (status === 'completed') return 'pipeline-stage-dot--completed'
  if (status === 'failed') return 'pipeline-stage-dot--failed'
  if (status === 'manual') return 'pipeline-stage-dot--manual'
  if (status === 'canceled') return 'pipeline-stage-dot--canceled'
  if (status === 'skipped') return 'pipeline-stage-dot--skipped'
  return 'pipeline-stage-dot--pending'
}

function connectorClass(status: PipelineStageVisualStatus): string {
  if (status === 'completed') return 'pipeline-connector--active'
  if (status === 'running') return 'pipeline-connector--running'
  return ''
}
</script>

<style scoped>
.pipeline-stage-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.2rem;
  height: 1.2rem;
  border-radius: 9999px;
  border: 1px solid transparent;
  font-size: 0.62rem;
  line-height: 1;
  font-weight: 700;
}

.pipeline-stage-dot--pending {
  background: rgb(71 85 105 / 0.25);
  border-color: rgb(148 163 184 / 0.4);
  color: rgb(203 213 225 / 0.95);
}

.pipeline-stage-dot--running {
  background: rgb(245 158 11 / 0.2);
  border-color: rgb(251 191 36 / 0.5);
  color: rgb(253 230 138 / 0.95);
  animation: stage-running-pulse 1.1s ease-in-out infinite;
}

.pipeline-stage-dot--completed {
  background: rgb(16 185 129 / 0.2);
  border-color: rgb(52 211 153 / 0.5);
  color: rgb(110 231 183 / 1);
}

.pipeline-stage-dot--failed {
  background: rgb(239 68 68 / 0.2);
  border-color: rgb(248 113 113 / 0.5);
  color: rgb(252 165 165 / 1);
}

.pipeline-stage-dot--manual {
  background: rgb(14 165 233 / 0.2);
  border-color: rgb(56 189 248 / 0.5);
  color: rgb(125 211 252 / 1);
}

.pipeline-stage-dot--canceled,
.pipeline-stage-dot--skipped {
  background: rgb(100 116 139 / 0.24);
  border-color: rgb(148 163 184 / 0.4);
  color: rgb(203 213 225 / 0.95);
}

.pipeline-connector {
  width: 1.25rem;
  height: 2px;
  border-radius: 9999px;
  background: rgb(100 116 139 / 0.45);
  transition: background-color 180ms ease;
}

.pipeline-connector--active {
  background: rgb(16 185 129 / 0.8);
}

.pipeline-connector--running {
  background: linear-gradient(90deg, rgb(245 158 11 / 0.5), rgb(245 158 11 / 0.95), rgb(245 158 11 / 0.5));
  background-size: 200% 100%;
  animation: connector-running-flow 1.2s linear infinite;
}

@keyframes stage-running-pulse {
  0% {
    box-shadow: 0 0 0 0 rgb(245 158 11 / 0.4);
  }
  70% {
    box-shadow: 0 0 0 7px rgb(245 158 11 / 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgb(245 158 11 / 0);
  }
}

@keyframes connector-running-flow {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: 0 0;
  }
}
</style>
