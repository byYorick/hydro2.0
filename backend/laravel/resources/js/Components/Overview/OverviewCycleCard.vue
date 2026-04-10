<template>
  <div class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4">
    <StageProgress
      v-if="activeGrowCycle && activeGrowCycle.recipeRevision"
      :grow-cycle="activeGrowCycle"
      :phase-progress="phaseProgress"
      :phase-days-elapsed="phaseDaysElapsed"
      :phase-days-total="phaseDaysTotal"
      :started-at="activeGrowCycle.started_at"
    />

    <div
      v-else-if="activeGrowCycle"
      class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-5"
    >
      <p class="text-sm font-semibold text-[color:var(--text-primary)]">
        Цикл выращивания активен
      </p>
      <div class="mt-2 space-y-1 text-xs text-[color:var(--text-muted)]">
        <div v-if="zoneStatus">
          Статус зоны:
          <span class="font-semibold text-[color:var(--text-primary)]">{{ translateStatus(zoneStatus) }}</span>
        </div>
        <div v-if="activeGrowCycle.status">
          Статус цикла:
          <span class="font-semibold text-[color:var(--text-primary)]">{{ translateStatus(activeGrowCycle.status) }}</span>
        </div>
        <div v-if="activeGrowCycle.started_at">
          Запущен: {{ formatTimeShort(new Date(activeGrowCycle.started_at)) }}
        </div>
        <p class="mt-2 text-[color:var(--text-dim)]">
          Привяжите рецепт для детального отслеживания прогресса фаз
        </p>
      </div>
    </div>

    <div
      v-else-if="zoneStatus === 'RUNNING' || zoneStatus === 'PAUSED'"
      class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-5"
    >
      <div class="flex items-center gap-2">
        <span
          class="ui-state-dot text-[color:var(--accent-cyan)]"
          title="Загрузка данных цикла"
        ></span>
        <p class="text-sm font-semibold text-[color:var(--text-primary)]">
          Данные цикла ещё загружаются
        </p>
      </div>
      <p class="mt-2 text-xs text-[color:var(--text-muted)]">
        Обновите данные зоны на вкладке «Цикл», чтобы синхронизировать активный цикл и таргеты
      </p>
    </div>

    <div
      v-else
      class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-5"
    >
      <p class="text-sm font-semibold text-[color:var(--text-primary)]">
        Цикл выращивания не запущен
      </p>
      <p class="mt-2 text-xs text-[color:var(--text-muted)]">
        Привяжите рецепт и запустите цикл выращивания для отслеживания прогресса
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import StageProgress from '@/Components/StageProgress.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTimeShort } from '@/utils/formatTime'

defineProps<{
  activeGrowCycle?: any
  zoneStatus?: string | null
  phaseProgress: number | null
  phaseDaysElapsed: number | null
  phaseDaysTotal: number | null
}>()
</script>
