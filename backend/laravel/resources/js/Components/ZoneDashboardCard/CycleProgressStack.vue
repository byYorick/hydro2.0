<template>
  <div
    v-if="hasData"
    class="space-y-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
  >
    <!-- Overall cycle -->
    <div>
      <div class="flex items-baseline justify-between text-[10px] text-[color:var(--text-muted)]">
        <span class="font-medium text-[color:var(--text-primary)]">
          Цикл
        </span>
        <span class="tabular-nums">
          {{ overallDayLabel }} · {{ overallPct }}%
        </span>
      </div>
      <div class="mt-1 h-1.5 w-full rounded-full bg-[color:var(--border-muted)] overflow-hidden">
        <div
          class="h-full bg-[color:var(--accent-green)] transition-all duration-500"
          :style="{ width: `${overallPct}%` }"
        ></div>
      </div>
    </div>

    <!-- Current phase -->
    <div v-if="phase">
      <div class="flex items-baseline justify-between text-[10px] text-[color:var(--text-muted)]">
        <span class="truncate">
          {{ phase.name }}
        </span>
        <span class="tabular-nums shrink-0">
          День {{ phase.dayElapsed }}/{{ phase.dayTotal }}
        </span>
      </div>
      <div class="mt-1 h-1 w-full rounded-full bg-[color:var(--border-muted)] overflow-hidden">
        <div
          class="h-full bg-[color:var(--accent-cyan)] transition-all duration-500"
          :style="{ width: `${phase.progress}%` }"
        ></div>
      </div>
    </div>
  </div>

  <div
    v-else
    class="rounded-lg border border-dashed border-[color:var(--border-muted)] px-3 py-2 text-xs text-[color:var(--text-muted)]"
  >
    Активный цикл не запущен
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface PhaseInfo {
  name: string
  dayElapsed: number
  dayTotal: number
  /** 0..100 */
  progress: number
}

interface Props {
  /** 0..100, общий прогресс цикла */
  overallPct: number | null
  /** Подпись дня цикла (например, "День 4/21"). Если не задана — скрывается. */
  overallDayLabel?: string | null
  /** Информация о текущей фазе (может отсутствовать) */
  phase?: PhaseInfo | null
}

const props = withDefaults(defineProps<Props>(), {
  overallDayLabel: null,
  phase: null,
})

const hasData = computed(() => props.overallPct !== null || props.phase !== null)

const overallPct = computed(() => {
  if (props.overallPct === null || Number.isNaN(props.overallPct)) return 0
  return Math.max(0, Math.min(100, Math.round(props.overallPct)))
})

const overallDayLabel = computed(() => props.overallDayLabel ?? '—')
</script>
