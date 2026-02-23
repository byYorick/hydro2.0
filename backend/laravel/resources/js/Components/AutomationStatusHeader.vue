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
      <ul class="mt-2 space-y-1">
        <li
          v-for="stage in setupStages"
          :key="stage.code"
          class="flex items-center justify-between gap-2 rounded-lg border border-[color:var(--border-muted)]/40 bg-[color:var(--surface-card)]/30 px-2 py-1.5"
        >
          <span class="text-xs text-[color:var(--text-primary)]">{{ stage.label }}</span>
          <span
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="stagePillClass(stage.status)"
          >
            {{ setupStageStatusLabel(stage.status) }}
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import StatusIndicator from '@/Components/StatusIndicator.vue'
import type { AutomationStateType, SetupStageStatus, SetupStageView } from '@/types/Automation'

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

function setupStageStatusLabel(status: SetupStageStatus): string {
  if (status === 'running') return 'Выполняется'
  if (status === 'completed') return 'Выполнено'
  if (status === 'failed') return 'Ошибка'
  return 'Ожидание'
}

function stagePillClass(status: SetupStageStatus): string {
  if (status === 'running') {
    return 'bg-amber-500/20 text-amber-300 border border-amber-400/40'
  }
  if (status === 'completed') {
    return 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/40'
  }
  if (status === 'failed') {
    return 'bg-red-500/20 text-red-300 border border-red-400/40'
  }
  return 'bg-slate-500/20 text-slate-300 border border-slate-400/40'
}
</script>
