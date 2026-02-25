<template>
  <div>
    <header class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="space-y-1">
        <p class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">автоматизация</p>
        <h3 class="text-base md:text-lg font-semibold text-[color:var(--text-primary)]">
          {{ stateLabel }}
        </h3>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <StatusIndicator
          :status="stateCode"
          :variant="stateVariant"
          :pulse="isProcessActive"
          :show-label="true"
        />
        <div class="text-sm text-[color:var(--text-muted)]">
          {{ progressSummary }}
        </div>
      </div>
    </header>

    <p
      v-if="errorMessage"
      class="mt-3 text-xs text-red-500"
    >
      {{ errorMessage }}
    </p>
    <p
      v-if="warningMessage"
      class="mt-3 text-xs text-amber-400"
    >
      {{ warningMessage }}
    </p>

    <section class="mt-3 rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/45 p-3">
      <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <h4 class="text-xs uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Этапы setup режима</h4>
        <p class="text-xs text-[color:var(--text-muted)]">
          Сейчас: {{ currentSetupStageLabel }}
        </p>
      </div>
      <ul class="mt-3 flex min-w-max items-center gap-0.5 overflow-x-auto pb-1">
        <li
          v-for="(stage, index) in setupStages"
          :key="stage.code"
          class="flex items-center"
        >
          <div class="min-w-[172px] rounded-lg border border-[color:var(--border-muted)]/40 bg-[color:var(--surface-card)]/30 px-2.5 py-2">
            <div class="flex items-center gap-2">
              <span
                class="pipeline-stage-dot"
                :class="stageDotClass(stage.status)"
                :title="setupStageStatusLabel(stage.status)"
              >
                {{ stageStatusIcon(stage.status) }}
              </span>
              <span class="line-clamp-2 text-[11px] leading-[1.2rem] text-[color:var(--text-primary)]">{{ stage.label }}</span>
            </div>
            <div class="mt-1.5">
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="stagePillClass(stage.status)"
              >
                {{ setupStageStatusLabel(stage.status) }}
              </span>
            </div>
          </div>
          <span
            v-if="index < setupStages.length - 1"
            class="pipeline-connector"
            :class="connectorClass(stage.status)"
            aria-hidden="true"
          />
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import StatusIndicator from '@/Components/StatusIndicator.vue'
import type { AutomationStateType, SetupStageStatus, SetupStageView } from '@/types/Automation'

type PipelineStageVisualStatus = SetupStageStatus | 'manual' | 'canceled' | 'skipped'

interface Props {
  stateCode: AutomationStateType
  stateLabel: string
  stateVariant: 'neutral' | 'info' | 'warning' | 'success'
  isProcessActive: boolean
  progressSummary: string
  errorMessage: string | null
  warningMessage: string | null
  setupStages: SetupStageView[]
  currentSetupStageLabel: string
}

defineProps<Props>()

function setupStageStatusLabel(status: PipelineStageVisualStatus): string {
  if (status === 'running') return 'Выполняется'
  if (status === 'completed') return 'Выполнено'
  if (status === 'failed') return 'Ошибка'
  if (status === 'manual') return 'Ручной запуск'
  if (status === 'canceled') return 'Отменено'
  if (status === 'skipped') return 'Пропущено'
  return 'Ожидание'
}

function stageStatusIcon(status: PipelineStageVisualStatus): string {
  if (status === 'completed') return '✓'
  if (status === 'failed') return '!'
  if (status === 'running') return '⟳'
  if (status === 'manual') return '▶'
  if (status === 'canceled') return '×'
  if (status === 'skipped') return '›'
  return '•'
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
  return 'bg-slate-500/20 text-slate-300 border border-slate-400/40'
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
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 9999px;
  border: 1px solid transparent;
  font-size: 0.68rem;
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
  width: 1.6rem;
  height: 2px;
  margin: 0 0.25rem;
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
