<template>
  <Dropdown align="right" width="48">
    <template #trigger>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--bg-elevated)] hover:border-[color:var(--border-strong)]"
      >
        Действия
        <svg class="h-3 w-3 text-[color:var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
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
        :disabled="loading.nextPhase"
        class="dropdown-action"
        @click="$emit('next-phase')"
      >
        Следующая фаза
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
}>()

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
</style>
