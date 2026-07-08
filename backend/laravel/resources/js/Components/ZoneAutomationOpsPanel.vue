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
          {{ controlModeLabels[automationControlMode] }}
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
          v-for="mode in controlModeAvailable"
          :key="mode"
          type="button"
          class="rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-150 min-w-[4.5rem]"
          :class="[
            automationControlMode === mode
              ? 'bg-[color:var(--accent,#3b82f6)] text-white shadow-sm'
              : 'text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]/60 hover:text-[color:var(--text-primary)]',
            !canSelectMode(mode) ? 'opacity-40 cursor-not-allowed' : '',
          ]"
          :disabled="!canSelectMode(mode) || automationControlModeLoading || automationControlModeSaving"
          :title="modeDisabledTitle(mode)"
          @click="$emit('select-mode', mode)"
        >
          <span
            v-if="automationControlModeSaving && pendingControlModeValue === mode"
            class="inline-block animate-spin mr-1 opacity-60"
          >⟳</span>
          {{ controlModeLabels[mode] }}
        </button>
      </div>
    </div>

    <!-- Тело: ручное управление + workflow steps -->
    <div class="grid gap-4 xl:grid-cols-2">
      <!-- Ручное управление -->
      <div class="space-y-2">
        <p class="text-xs text-[color:var(--text-muted)]">
          Ручное управление
        </p>
        <div class="grid gap-2 grid-cols-1 sm:grid-cols-3">
          <Button
            size="sm"
            :disabled="!canOperateAutomation || irrigationActionLoading"
            @click="$emit('start-irrigation')"
          >
            {{ irrigationActionLoading ? 'Отправка...' : 'Запустить полив' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || irrigationActionLoading"
            @click="$emit('force-irrigation')"
          >
            {{ irrigationActionLoading ? 'Отправка...' : 'Принудительный полив' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canOperateAutomation || diagnosticsActionLoading"
            @click="$emit('run-diagnostics')"
          >
            {{ diagnosticsActionLoading ? 'Отправка...' : 'Диагностика' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || solutionChangeActionLoading"
            @click="$emit('start-solution-change')"
          >
            {{ solutionChangeActionLoading ? 'Отправка...' : 'Подмена раствора' }}
          </Button>
        </div>
      </div>

      <!-- Ручные шаги workflow -->
      <div class="space-y-2">
        <p class="text-xs text-[color:var(--text-muted)]">
          Ручные шаги workflow:
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
          class="text-xs text-[color:var(--text-dim)] leading-relaxed"
        >
          <template v-if="manualStepsIdleHint">
            {{ manualStepsIdleHint }}
          </template>
          <template v-else>
            Для текущей стадии workflow нет доступных ручных шагов.
          </template>
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
import {
  CONTROL_MODE_LABELS,
  controlModeDisabledReason,
  isControlModeTransitionAllowed,
} from '@/utils/zoneAutomationControlMode'

type ModeValue = 'auto' | 'semi' | 'manual'

interface Props {
  canOperateAutomation: boolean
  userRole: string
  automationControlMode: AutomationControlMode
  controlModeAvailable: AutomationControlMode[]
  allowedManualSteps: AutomationManualStep[]
  automationControlModeLoading: boolean
  automationControlModeSaving: boolean
  manualStepLoading: Record<AutomationManualStep, boolean>
  pendingControlModeValue: ModeValue | null
  automationStateMetaLabel: string | null
  irrigationActionLoading?: boolean
  diagnosticsActionLoading?: boolean
  solutionChangeActionLoading?: boolean
  currentStage?: string | null
  workflowPhase?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  irrigationActionLoading: false,
  diagnosticsActionLoading: false,
  solutionChangeActionLoading: false,
  currentStage: null,
  workflowPhase: null,
})

const controlModeLabels = CONTROL_MODE_LABELS

function canSelectMode(mode: AutomationControlMode): boolean {
  if (!props.canOperateAutomation) {
    return false
  }
  return isControlModeTransitionAllowed(
    props.userRole,
    props.automationControlMode,
    mode,
  )
}

function modeDisabledTitle(mode: AutomationControlMode): string | undefined {
  const reason = controlModeDisabledReason(
    props.userRole,
    props.automationControlMode,
    mode,
  )
  return reason ?? undefined
}

defineEmits<{
  (e: 'start-irrigation'): void
  (e: 'force-irrigation'): void
  (e: 'run-diagnostics'): void
  (e: 'start-solution-change'): void
  (e: 'select-mode', mode: ModeValue): void
  (e: 'run-manual-step', step: AutomationManualStep): void
}>()

const MANUAL_STEP_LABELS: Record<AutomationManualStep, string> = {
  clean_fill_start: 'Набрать чистую воду',
  clean_fill_stop: 'Стоп набор чистой',
  solution_fill_start: 'Набрать раствор',
  force_solution_fill_start: 'Форс: начать раствор',
  solution_fill_stop: 'Стоп набор раствора',
  prepare_recirculation_stop: 'Стоп рециркуляции setup',
  irrigation_stop: 'Стоп полива',
  irrigation_recovery_stop: 'Стоп рециркуляции полива',
  solution_drain_confirm: 'Подтвердить слив',
  solution_refill_confirm: 'Подтвердить наполнение',
  solution_change_abort: 'Отменить подмену',
}

const STEP_VARIANTS: Record<AutomationManualStep, 'secondary' | 'outline'> = {
  clean_fill_start: 'secondary',
  clean_fill_stop: 'outline',
  solution_fill_start: 'secondary',
  force_solution_fill_start: 'outline',
  solution_fill_stop: 'outline',
  prepare_recirculation_stop: 'outline',
  irrigation_stop: 'outline',
  irrigation_recovery_stop: 'outline',
  solution_drain_confirm: 'secondary',
  solution_refill_confirm: 'secondary',
  solution_change_abort: 'outline',
}

const visibleManualSteps = computed(() => {
  return props.allowedManualSteps.map((code) => ({
    code,
    label: MANUAL_STEP_LABELS[code],
    variant: STEP_VARIANTS[code],
  }))
})

const manualStepsIdleHint = computed(() => {
  if (props.automationControlMode === 'auto') {
    return null
  }
  const phase = String(props.workflowPhase ?? '').trim().toLowerCase()
  const stage = String(props.currentStage ?? '').trim()
  if (phase === 'idle' && !stage) {
    return 'Нет активной задачи AE3. В manual/semi шаги появляются после запуска workflow — нажмите «Диагностика».'
  }
  if (!stage) {
    return 'Стадия workflow не определена. Дождитесь обновления состояния или запустите «Диагностика».'
  }
  return null
})
</script>
