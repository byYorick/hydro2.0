<template>
  <Dropdown
    align="right"
    width="48"
  >
    <template #trigger>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--bg-elevated)] hover:border-[color:var(--border-strong)]"
      >
        Действия
        <svg
          class="h-3 w-3 text-[color:var(--text-muted)]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>
    </template>
    <template #content>
      <!-- Полив -->
      <button
        v-if="canOperate"
        type="button"
        :disabled="loading.irrigate"
        class="dropdown-action"
        @click="$emit('start-irrigation')"
      >
        Запустить полив
      </button>
      <button
        v-if="canOperate"
        type="button"
        :disabled="loading.irrigate"
        class="dropdown-action"
        @click="$emit('force-irrigation')"
      >
        Принудительный полив
      </button>

      <div
        v-if="canOperate && canManage && isActive"
        class="my-1 border-t border-[color:var(--border-muted)]"
      ></div>

      <!-- Управление циклом -->
      <button
        v-if="canManage && cycleStatus === 'RUNNING'"
        type="button"
        :disabled="loading.cyclePause"
        class="dropdown-action"
        @click="$emit('pause')"
      >
        Пауза
      </button>
      <button
        v-if="canManage && cycleStatus === 'PAUSED'"
        type="button"
        :disabled="loading.cycleResume"
        class="dropdown-action"
        @click="$emit('resume')"
      >
        Продолжить
      </button>
      <button
        v-if="canManage && isActive"
        type="button"
        :disabled="loading.nextPhase || nextPhaseDisabled"
        :title="nextPhaseHint ?? undefined"
        class="dropdown-action"
        :class="phaseReadyBadge ? 'dropdown-action--ready' : ''"
        @click="$emit('next-phase')"
      >
        <span class="flex items-center justify-between gap-2">
          <span>Следующая фаза</span>
          <span
            v-if="phaseReadyBadge"
            class="text-[11px] rounded-full bg-emerald-500/15 text-emerald-500 px-1.5 py-0.5"
          >готова</span>
          <span
            v-else-if="controlMode === 'auto'"
            class="text-[11px] text-[color:var(--text-dim)]"
          >авто</span>
        </span>
      </button>

      <div
        v-if="canManage && isActive"
        class="my-1 border-t border-[color:var(--border-muted)]"
      ></div>

      <button
        v-if="canManage && isActive"
        type="button"
        :disabled="loading.cycleHarvest"
        class="dropdown-action text-[color:var(--accent-green)]"
        @click="$emit('harvest')"
      >
        Урожай
      </button>
      <button
        v-if="canManage && isActive"
        type="button"
        :disabled="loading.cycleAbort"
        class="dropdown-action text-[color:var(--accent-red)]"
        @click="$emit('abort')"
      >
        Прервать цикл
      </button>
    </template>
  </Dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Dropdown from '@/Components/Dropdown.vue'
import type { GrowCycleStatus } from '@/types/GrowCycle'
import type { AutomationControlMode } from '@/types/Automation'

interface CycleLoadingState {
  irrigate: boolean
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

const props = defineProps<{
  cycleStatus: GrowCycleStatus | null
  canManage: boolean
  canOperate: boolean
  loading: CycleLoadingState
  /**
   * Control mode зоны. В `auto` advance выполняется cron-ом, UI-кнопка
   * блокируется. В `semi`/`manual` agronomist нажимает вручную; при
   * достижении duration показывается badge "готова".
   * См. CONTROL_MODES_SPEC.md §4.5.
   */
  controlMode?: AutomationControlMode | null
  /**
   * true если phase_started_at + duration_hours/days уже прошло (фаза готова).
   * Вычисляется родителем (Zone page) — фронт не дёргает backend на каждый tick.
   */
  phaseDurationComplete?: boolean
}>()

const nextPhaseDisabled = computed<boolean>(() => props.controlMode === 'auto')
const nextPhaseHint = computed<string | null>(() => {
  if (props.controlMode === 'auto') {
    return 'В режиме auto фаза переключается автоматически по таймеру. Смените на semi/manual чтобы управлять вручную.'
  }
  if (props.phaseDurationComplete) {
    return 'Длительность фазы истекла — можно переходить к следующей.'
  }
  return null
})
const phaseReadyBadge = computed<boolean>(
  () => props.controlMode !== 'auto' && props.phaseDurationComplete === true,
)

defineEmits<{
  'start-irrigation': []
  'force-irrigation': []
  'pause': []
  'resume': []
  'harvest': []
  'abort': []
  'next-phase': []
}>()

const isActive = computed(() =>
  props.cycleStatus === 'RUNNING' || props.cycleStatus === 'PAUSED',
)
</script>

<style scoped>
.dropdown-action {
  display: block;
  width: 100%;
  padding: 0.5rem 1rem;
  text-align: start;
  font-size: 0.875rem;
  line-height: 1.25rem;
  transition: background-color 150ms ease-in-out;
}

.dropdown-action:hover:not(:disabled) {
  background-color: var(--bg-elevated);
}

.dropdown-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dropdown-action--ready {
  background-color: color-mix(in srgb, var(--accent-green, #10b981) 8%, transparent);
}
</style>
