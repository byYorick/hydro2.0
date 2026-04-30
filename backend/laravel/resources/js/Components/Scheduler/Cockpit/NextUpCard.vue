<template>
  <section
    class="next-up-card rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3.5"
    data-testid="scheduler-next-up"
  >
    <div class="flex items-center justify-between gap-2">
      <div class="text-[10px] font-bold tracking-[0.15em] text-[color:var(--text-dim)]">
        ДАЛЬШЕ В ОЧЕРЕДИ
      </div>
      <span
        v-if="windows.length > 0"
        class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]"
      >
        {{ windows.length }} окон
      </span>
    </div>

    <div
      v-if="windows.length === 0"
      class="mt-2 text-[11px] text-[color:var(--text-muted)]"
    >
      В ближайшем горизонте нет запланированных окон.
    </div>

    <div
      v-else
      class="mt-2 flex flex-col gap-1.5"
    >
      <div
        v-for="(window, index) in visibleWindows"
        :key="window.plan_window_id"
        class="next-up-card__row grid items-center gap-2 rounded-xl border px-2.5 py-2"
        :class="index === 0
          ? 'border-[color:var(--accent-green)]/40 bg-[color:var(--accent-green)]/10'
          : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40'"
        :style="{ gridTemplateColumns: '24px minmax(0,1fr) auto' }"
        :data-testid="`scheduler-next-up-row-${window.plan_window_id}`"
      >
        <span
          class="inline-flex h-6 w-6 items-center justify-center rounded-lg border text-[10px] font-bold"
          :style="{
            color: accentFor(window),
            borderColor: `color-mix(in srgb, ${accentFor(window)} 42%, transparent)`,
            background: `color-mix(in srgb, ${accentFor(window)} 12%, transparent)`,
          }"
        >{{ index + 1 }}</span>
        <div class="min-w-0">
          <div class="truncate text-[12px] font-semibold text-[color:var(--text-primary)]">
            {{ laneLabel(window.task_type) }}
          </div>
          <div class="truncate text-[10px] text-[color:var(--text-muted)]">
            {{ formatDateTime?.(window.trigger_at) ?? window.trigger_at }}
          </div>
        </div>
        <span
          class="rounded-full px-2 py-1 tabular-nums text-[12px] font-semibold"
          :class="index === 0 ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--text-dim)]'"
        >{{ formatRelative?.(window.trigger_at) ?? relativeFallback(window.trigger_at) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlanWindow } from '@/composables/zoneScheduleWorkspaceTypes'

interface Props {
  windows: PlanWindow[]
  maxItems?: number
  laneLabel?: (taskType: string) => string
  formatDateTime?: (value: string | null | undefined) => string
  formatRelative?: (value: string | null | undefined) => string
}

const props = withDefaults(defineProps<Props>(), {
  maxItems: 3,
  laneLabel: (taskType: string) => taskType,
  formatDateTime: undefined,
  formatRelative: undefined,
})

const visibleWindows = computed(() => props.windows.slice(0, props.maxItems))

const LANE_ACCENT: Record<string, string> = {
  irrigation: 'var(--accent-green)',
  irrigation_tick: 'var(--accent-green)',
  lighting: 'var(--accent-amber)',
  lighting_tick: 'var(--accent-amber)',
  ph_correction: 'var(--accent-cyan)',
  ec_correction: 'var(--accent-cyan)',
  diagnostics: 'var(--text-dim)',
}

function accentFor(window: PlanWindow): string {
  return LANE_ACCENT[window.task_type] ?? 'var(--text-dim)'
}

function relativeFallback(iso: string | null | undefined): string {
  if (!iso) return ''
  const target = new Date(iso).getTime()
  if (Number.isNaN(target)) return ''
  const diffSec = Math.round((target - Date.now()) / 1000)
  if (diffSec <= 0) return 'сейчас'
  const min = Math.round(diffSec / 60)
  if (min < 60) return `${min}м`
  const hours = Math.round(min / 60)
  return `${hours}ч`
}
</script>

<style scoped>
.next-up-card {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.next-up-card__row {
  transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease;
}

.next-up-card__row:hover {
  transform: translateX(2px);
  border-color: var(--border-strong);
}
</style>
