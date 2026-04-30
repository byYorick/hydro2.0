<template>
  <section
    class="swimlane-panel flex min-h-0 flex-1 flex-col rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3.5"
    data-testid="scheduler-swimlane"
  >
    <header class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <h4 class="m-0 text-[13px] font-semibold text-[color:var(--text-primary)]">
          Лента исполнений
        </h4>
        <Badge
          variant="neutral"
          size="xs"
        >
          {{ horizonLabel }}
        </Badge>
      </div>
      <div class="flex flex-wrap items-center gap-1">
        <span class="swim-pill">
          <span class="swim-dot bg-[color:var(--accent-green)]"></span> OK
        </span>
        <span class="swim-pill">
          <span class="swim-dot bg-[color:var(--accent-red)]"></span> FAIL
        </span>
        <span class="swim-pill">
          <span class="swim-dot bg-[color:var(--text-dim)]"></span> SKIP
        </span>
        <span class="swim-pill">
          <span class="swim-dot bg-[color:var(--accent-amber)]"></span> PLAN
        </span>
      </div>
    </header>

    <div
      v-if="lanes.length === 0"
      class="mt-3 text-[12px] text-[color:var(--text-muted)]"
    >
      На выбранном горизонте ещё нет исполнений.
    </div>

    <div
      v-else
      class="mt-3 flex flex-1 flex-col gap-2"
    >
      <div
        v-for="lane in lanes"
        :key="lane.lane"
        class="grid items-center gap-3"
        :style="{ gridTemplateColumns: '128px minmax(0,1fr)' }"
      >
        <div class="min-w-0">
          <span class="block truncate text-[11px] font-semibold text-[color:var(--text-primary)]">
            {{ lane.lane }}
          </span>
          <span class="text-[9px] text-[color:var(--text-muted)]">{{ lane.runs.length }} событий</span>
        </div>
        <div class="swim-track relative h-8 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40">
          <div
            class="absolute top-[-4px] bottom-[-4px] z-10 w-px bg-[color:var(--accent-cyan)] shadow-[0_0_12px_color-mix(in_srgb,var(--accent-cyan)_45%,transparent)]"
            style="left: 50%"
          ></div>
          <div
            class="absolute left-1/2 top-1/2 z-10 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[color:var(--accent-cyan)]"
          ></div>
          <div
            v-for="(point, index) in lane.runs"
            :key="`${lane.lane}-${index}`"
            class="swim-point absolute top-2 rounded-[4px]"
            :class="point.s === 'run' ? 'h-4 w-[18px]' : 'h-4 w-2.5'"
            :style="{
              left: `${point.t}%`,
              background: STATUS_COLOR[point.s],
              transform: 'translateX(-50%)',
              boxShadow: point.s === 'run'
                ? '0 0 0 3px color-mix(in srgb, var(--accent-cyan) 25%, transparent)'
                : 'none',
            }"
            :title="`${lane.lane} · ${point.s}`"
          ></div>
        </div>
      </div>
    </div>

    <footer
      class="mt-2.5 grid gap-3 text-[9px] text-[color:var(--text-muted)]"
      :style="{ gridTemplateColumns: '128px minmax(0,1fr)' }"
    >
      <span></span>
      <div class="flex justify-between">
        <span>{{ rulerLabels[0] }}</span>
        <span>{{ rulerLabels[1] }}</span>
        <span class="font-semibold text-[color:var(--accent-cyan)]">{{ rulerLabels[2] }} ●</span>
        <span>{{ rulerLabels[3] }}</span>
        <span>{{ rulerLabels[4] }}</span>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { LaneHistory, LaneHistoryStatus } from '@/composables/zoneScheduleWorkspaceTypes'

interface Props {
  lanes: LaneHistory[]
  horizon: '24h' | '7d'
  now?: Date
}

const props = withDefaults(defineProps<Props>(), {
  now: undefined,
})

const STATUS_COLOR: Record<LaneHistoryStatus, string> = {
  ok: 'var(--accent-green)',
  err: 'var(--accent-red)',
  skip: 'var(--text-dim)',
  run: 'var(--accent-cyan)',
  warn: 'var(--accent-amber)',
}

const horizonLabel = computed(() =>
  props.horizon === '7d'
    ? '3.5д назад → сейчас → +3.5д'
    : '12ч назад → сейчас → +12ч',
)

const rulerLabels = computed<string[]>(() => {
  const nowRef = props.now ?? new Date()
  const halfHours = props.horizon === '7d' ? 12 * 7 / 2 : 12
  const quarter = halfHours / 2
  const offsets = [-halfHours, -quarter, 0, quarter, halfHours]
  return offsets.map((offsetHours) => formatLabel(nowRef, offsetHours))
})

function formatLabel(reference: Date, offsetHours: number): string {
  const target = new Date(reference.getTime() + offsetHours * 60 * 60 * 1000)
  const hh = String(target.getHours()).padStart(2, '0')
  const mm = String(target.getMinutes()).padStart(2, '0')
  if (props.horizon === '7d') {
    const dd = String(target.getDate()).padStart(2, '0')
    const mo = String(target.getMonth() + 1).padStart(2, '0')
    return `${dd}.${mo} ${hh}:${mm}`
  }
  return `${hh}:${mm}`
}
</script>

<style scoped>
.swim-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--text-dim) 10%, transparent);
  color: var(--text-dim);
  font-size: 10px;
  font-weight: 500;
  border: 1px solid var(--border-muted);
}

.swimlane-panel {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.swim-track {
  overflow: hidden;
  background-image:
    linear-gradient(90deg, transparent 0, transparent calc(25% - 1px), color-mix(in srgb, var(--border-muted) 54%, transparent) 25%, transparent calc(25% + 1px)),
    linear-gradient(90deg, transparent 0, transparent calc(75% - 1px), color-mix(in srgb, var(--border-muted) 54%, transparent) 75%, transparent calc(75% + 1px));
}

.swim-point {
  z-index: 11;
  border: 1px solid color-mix(in srgb, #fff 32%, transparent);
}

.swim-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 999px;
}
</style>
