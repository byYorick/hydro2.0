<template>
  <div
    class="rounded-md border border-[var(--border-muted)] p-2.5 bg-[var(--bg-elevated)]"
    :class="enabled ? '' : 'opacity-55'"
  >
    <div
      class="relative h-7 rounded-sm overflow-hidden"
      style="background: linear-gradient(90deg, #1a2832 0%, #1a2832 100%);"
    >
      <div
        class="absolute top-0 bottom-0"
        :style="{
          left: `${startPct}%`,
          width: `${Math.max(0, endPct - startPct)}%`,
          background: 'linear-gradient(180deg, #f5d97a, #e8a93c)',
        }"
      ></div>
      <div
        class="absolute top-0 bottom-0 w-px bg-white/60"
        :style="{ left: `${startPct}%` }"
      ></div>
      <div
        class="absolute top-0 bottom-0 w-px bg-white/60"
        :style="{ left: `${endPct}%` }"
      ></div>
      <div
        v-for="hour in [0, 6, 12, 18, 24]"
        :key="hour"
        class="absolute top-0 bottom-0 w-px bg-white/10"
        :style="{ left: `${(hour / 24) * 100}%` }"
      ></div>
    </div>
    <div class="flex justify-between mt-1.5 font-mono text-[10px] text-[var(--text-dim)]">
      <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
    </div>
    <div class="flex gap-3.5 mt-1.5 text-[11px] text-[var(--text-muted)] flex-wrap">
      <span>
        День: <span class="font-mono">{{ scheduleStart }}–{{ scheduleEnd }}</span>
        <span v-if="luxDay != null"> · {{ luxDay }} lux</span>
      </span>
      <span v-if="luxNight != null">
        Ночь: <span class="font-mono">{{ luxNight }}</span> lux
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    scheduleStart?: string
    scheduleEnd?: string
    luxDay?: number | null
    luxNight?: number | null
    enabled?: boolean
  }>(),
  {
    scheduleStart: '06:00',
    scheduleEnd: '18:00',
    luxDay: null,
    luxNight: null,
    enabled: true,
  },
)

function timeToPct(value: string): number {
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(value ?? '')
  if (!match) return 0
  const h = Number(match[1])
  const m = Number(match[2])
  if (Number.isNaN(h) || Number.isNaN(m)) return 0
  return Math.max(0, Math.min(100, ((h * 60 + m) / 1440) * 100))
}

const startPct = computed(() => timeToPct(props.scheduleStart))
const endPct = computed(() => timeToPct(props.scheduleEnd))
</script>
