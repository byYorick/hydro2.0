<template>
  <section
    class="flex min-h-0 flex-1 flex-col rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-3"
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
      class="mt-2.5 flex flex-1 flex-col gap-1.5"
    >
      <div
        v-for="lane in lanes"
        :key="lane.lane"
        class="grid items-center gap-2.5"
        :style="{ gridTemplateColumns: '120px minmax(0,1fr)' }"
      >
        <span class="truncate text-[11px] font-medium text-[color:var(--text-dim)]">
          {{ lane.lane }}
        </span>
        <div class="relative h-6 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40">
          <div
            class="absolute top-[-2px] bottom-[-2px] w-px bg-[color:var(--accent-cyan)]"
            style="left: 50%"
          ></div>
          <div
            v-for="(point, index) in lane.runs"
            :key="`${lane.lane}-${index}`"
            class="absolute top-1 rounded-[3px]"
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
      class="mt-2 grid gap-2.5 text-[9px] text-[color:var(--text-muted)]"
      :style="{ gridTemplateColumns: '120px minmax(0,1fr)' }"
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

.swim-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 999px;
}
</style>
