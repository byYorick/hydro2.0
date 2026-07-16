<template>
  <Dropdown
    v-if="canManage || canManageRecipe"
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
        v-if="canManage && cycleStatus === 'PLANNED'"
        type="button"
        :disabled="loading.cycleAbort"
        class="dropdown-action text-[color:var(--accent-red)]"
        @click="$emit('abort')"
      >
        Отменить запланированный
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
      <div
        v-if="canManageRecipe && isActive"
        class="my-1 border-t border-[color:var(--border-muted)]"
      ></div>
      <button
        v-if="canManageRecipe && isActive"
        type="button"
        class="dropdown-action"
        data-testid="cycle-change-recipe"
        @click="$emit('change-recipe')"
      >
        Сменить рецепт
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
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

const props = withDefaults(defineProps<{
  cycleStatus: GrowCycleStatus | null
  canManage: boolean
  canManageRecipe?: boolean
  loading: CycleLoadingState
  controlMode?: AutomationControlMode | null
  phaseDurationComplete?: boolean
}>(), {
  canManageRecipe: false,
})

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
  'pause': []
  'resume': []
  'harvest': []
  'abort': []
  'next-phase': []
  'change-recipe': []
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
