<template>
  <div
    v-if="hasCycle"
    class="space-y-2.5 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/55 p-3"
  >
    <div>
      <div class="flex items-baseline justify-between gap-2 text-[10px] text-[color:var(--text-muted)]">
        <span class="font-semibold uppercase tracking-[0.12em] text-[color:var(--text-primary)]">
          Цикл
        </span>
        <span class="tabular-nums">
          {{ overallDayLabel }} · {{ overallPct }}%
        </span>
      </div>
      <div class="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--border-muted)]">
        <div
          class="h-full rounded-full bg-[linear-gradient(90deg,var(--accent-green),var(--accent-cyan))] transition-all duration-500"
          :style="{ width: `${overallPct}%` }"
        />
      </div>
    </div>

    <div v-if="phase">
      <div class="flex items-baseline justify-between gap-2 text-[10px] text-[color:var(--text-muted)]">
        <span class="truncate">
          {{ phase.name }}
        </span>
        <span class="shrink-0 tabular-nums">
          День {{ phase.dayElapsed }}/{{ phase.dayTotal }}
        </span>
      </div>
      <div class="mt-1 h-1 w-full overflow-hidden rounded-full bg-[color:var(--border-muted)]">
        <div
          class="h-full rounded-full bg-[color:var(--accent-cyan)] transition-all duration-500"
          :style="{ width: `${phase.progress}%` }"
        />
      </div>
    </div>
  </div>

  <div
    v-else
    class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-3 py-3 text-center text-xs text-[color:var(--text-muted)]"
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
  /** true если zone.cycle существует — empty-state только при cycle == null */
  hasCycle?: boolean
  /** 0..100, общий прогресс цикла */
  overallPct: number | null
  /** Подпись дня цикла (например, "День 4/21"). Если не задана — статус или «—». */
  overallDayLabel?: string | null
  /** Короткий статус цикла, когда нет day-label */
  statusLabel?: string | null
  /** Информация о текущей фазе (может отсутствовать) */
  phase?: PhaseInfo | null
}

const props = withDefaults(defineProps<Props>(), {
  hasCycle: false,
  overallDayLabel: null,
  statusLabel: null,
  phase: null,
})

const overallPct = computed(() => {
  if (props.overallPct === null || Number.isNaN(props.overallPct)) return 0
  return Math.max(0, Math.min(100, Math.round(props.overallPct)))
})

const overallDayLabel = computed(
  () => props.overallDayLabel ?? props.statusLabel ?? '—',
)
</script>
