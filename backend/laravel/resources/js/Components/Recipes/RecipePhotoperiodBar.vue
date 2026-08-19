<template>
  <div
    class="space-y-1"
    data-testid="recipe-photoperiod-bar"
  >
    <div class="flex items-center justify-between text-[11px] text-[color:var(--text-muted)]">
      <span>Световой день</span>
      <span class="font-mono text-[color:var(--text-primary)]">{{ summaryLabel }}</span>
    </div>

    <div class="relative h-4 w-full overflow-hidden rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
      <span
        v-for="(segment, position) in segments"
        :key="`light-${position}`"
        class="absolute inset-y-0 bg-[color:var(--accent-amber)] opacity-70"
        :style="{ left: `${segment.leftPct}%`, width: `${segment.widthPct}%` }"
      ></span>
    </div>

    <div class="flex justify-between text-[10px] text-[color:var(--text-dim)]">
      <span>00:00</span>
      <span>06:00</span>
      <span>12:00</span>
      <span>18:00</span>
      <span>24:00</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatNumberValue, formatTimeOfDay } from '@/utils/recipeVisualization'

const props = defineProps<{
  photoperiodHours: number | null
  startTime: string | null
}>()

const startHour = computed(() => {
  const match = /^(\d{1,2}):(\d{2})/.exec(props.startTime ?? '')
  if (!match) {
    return 0
  }

  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return 0
  }

  return ((hours + minutes / 60) % 24 + 24) % 24
})

const clampedHours = computed(() => {
  const hours = props.photoperiodHours
  if (hours === null || !Number.isFinite(hours) || hours <= 0) {
    return 0
  }

  return Math.min(hours, 24)
})

/** Световой период может пересекать полночь, поэтому он рисуется двумя сегментами. */
const segments = computed(() => {
  const duration = clampedHours.value
  if (duration <= 0) {
    return []
  }

  const start = startHour.value
  const end = start + duration
  if (end <= 24) {
    return [{ leftPct: (start / 24) * 100, widthPct: (duration / 24) * 100 }]
  }

  return [
    { leftPct: (start / 24) * 100, widthPct: ((24 - start) / 24) * 100 },
    { leftPct: 0, widthPct: ((end - 24) / 24) * 100 },
  ]
})

const summaryLabel = computed(() => {
  if (clampedHours.value <= 0) {
    return '—'
  }

  return `${formatNumberValue(clampedHours.value, 1)} ч с ${formatTimeOfDay(props.startTime) === '—' ? '00:00' : formatTimeOfDay(props.startTime)}`
})
</script>
