<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
    <!-- Шапка: режим управления -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">Режим</span>
        <Badge
          v-if="!automationControlModeLoading"
          :variant="automationControlMode === 'auto' ? 'info' : 'warning'"
        >
          {{ automationControlMode }}
        </Badge>
        <span
          v-else
          class="text-xs text-[color:var(--text-dim)] animate-pulse"
        >загрузка...</span>
        <span
          v-if="automationStateMetaLabel"
          class="text-xs text-[color:var(--text-muted)]"
        >· {{ automationStateMetaLabel }}</span>
      </div>
      <div
        class="inline-flex gap-1 rounded-xl border border-[color:var(--border-muted)] p-1 bg-[color:var(--surface-card)]"
        :class="{ 'opacity-60': automationControlModeLoading }"
      >
        <button
          v-for="mode in (['auto', 'semi', 'manual'] as const)"
          :key="mode"
          type="button"
          class="rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-150 min-w-[4.5rem]"
          :class="[
            automationControlMode === mode
              ? 'bg-[color:var(--accent,#3b82f6)] text-white shadow-sm'
              : 'text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]/60 hover:text-[color:var(--text-primary)]',
          ]"
          :disabled="!canOperateAutomation || automationControlModeLoading || automationControlModeSaving"
          @click="$emit('select-mode', mode)"
        >
          <span
            v-if="automationControlModeSaving && pendingControlModeValue === mode"
            class="inline-block animate-spin mr-1 opacity-60"
          >⟳</span>
          {{ mode }}
        </button>
      </div>
    </div>

    <!-- Тело: быстрые команды + ручные шаги -->
    <div class="grid gap-4 xl:grid-cols-2">
      <!-- Быстрые команды -->
      <div class="space-y-2">
        <p class="text-xs text-[color:var(--text-muted)]">
          Операционные команды
        </p>
        <div class="grid gap-2 grid-cols-2 sm:grid-cols-3 xl:grid-cols-2 2xl:grid-cols-3">
          <Button
            size="sm"
            :disabled="!canOperateAutomation || quickActions.irrigation"
            @click="$emit('manual-irrigation')"
          >
            {{ quickActions.irrigation ? 'Отправка...' : 'Запустить полив' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canOperateAutomation || quickActions.lighting"
            @click="$emit('manual-lighting')"
          >
            {{ quickActions.lighting ? 'Отправка...' : 'Применить свет' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || quickActions.ph"
            @click="$emit('manual-ph')"
          >
            {{ quickActions.ph ? 'Отправка...' : 'Дать target pH' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || quickActions.ec"
            @click="$emit('manual-ec')"
          >
            {{ quickActions.ec ? 'Отправка...' : 'Дать target EC' }}
          </Button>
        </div>
      </div>

      <!-- Ручные шаги -->
      <div class="space-y-2">
        <p class="text-xs text-[color:var(--text-muted)]">
          Ручные шаги:
          <span
            v-if="automationControlMode === 'auto'"
            class="text-[color:var(--text-dim)]"
          >недоступны в режиме <code>auto</code></span>
          <span
            v-else
            class="text-emerald-500 dark:text-emerald-400"
          >доступны в режиме <code>{{ automationControlMode }}</code></span>
        </p>
        <div
          v-if="visibleManualSteps.length > 0"
          class="grid gap-2 grid-cols-2"
        >
          <Button
            v-for="step in visibleManualSteps"
            :key="step.code"
            size="sm"
            :variant="step.variant"
            :disabled="!canOperateAutomation || automationControlMode === 'auto' || manualStepLoading[step.code]"
            @click="$emit('run-manual-step', step.code)"
          >
            {{ manualStepLoading[step.code] ? 'Отправка...' : step.label }}
          </Button>
        </div>
        <p
          v-else
          class="text-xs text-[color:var(--text-dim)]"
        >
          Для текущей фазы нет доступных ручных шагов.
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import type { AutomationControlMode, AutomationManualStep } from '@/types/Automation'

type ModeValue = 'auto' | 'semi' | 'manual'

interface QuickActionsState {
  irrigation: boolean
  lighting: boolean
  ph: boolean
  ec: boolean
}

interface Props {
  canOperateAutomation: boolean
  quickActions: QuickActionsState
  automationControlMode: AutomationControlMode
  allowedManualSteps: AutomationManualStep[]
  automationControlModeLoading: boolean
  automationControlModeSaving: boolean
  manualStepLoading: Record<AutomationManualStep, boolean>
  pendingControlModeValue: ModeValue | null
  automationStateMetaLabel: string | null
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'manual-irrigation'): void
  (e: 'manual-lighting'): void
  (e: 'manual-ph'): void
  (e: 'manual-ec'): void
  (e: 'select-mode', mode: ModeValue): void
  (e: 'run-manual-step', step: AutomationManualStep): void
}>()

const MANUAL_STEP_LABELS: Record<AutomationManualStep, string> = {
  clean_fill_start: 'Набрать чистую воду',
  clean_fill_stop: 'Стоп набор чистой',
  solution_fill_start: 'Набрать раствор',
  solution_fill_stop: 'Стоп набор раствора',
  prepare_recirculation_start: 'Старт рециркуляции setup',
  prepare_recirculation_stop: 'Стоп рециркуляции setup',
  irrigation_stop: 'Стоп полива',
  irrigation_recovery_start: 'Старт рециркуляции полива',
  irrigation_recovery_stop: 'Стоп рециркуляции полива',
}

const STEP_VARIANTS: Record<AutomationManualStep, 'secondary' | 'outline'> = {
  clean_fill_start: 'secondary',
  clean_fill_stop: 'outline',
  solution_fill_start: 'secondary',
  solution_fill_stop: 'outline',
  prepare_recirculation_start: 'secondary',
  prepare_recirculation_stop: 'outline',
  irrigation_stop: 'outline',
  irrigation_recovery_start: 'secondary',
  irrigation_recovery_stop: 'outline',
}

const visibleManualSteps = computed(() => {
  return props.allowedManualSteps.map((code) => ({
    code,
    label: MANUAL_STEP_LABELS[code],
    variant: STEP_VARIANTS[code],
  }))
})
</script>
