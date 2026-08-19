<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between gap-2 text-xs">
      <span class="text-[color:var(--text-muted)]">
        Длительность цикла: <span class="font-semibold text-[color:var(--text-primary)]">{{ totalLabel }}</span>
      </span>
      <span
        v-if="hasUnknownDuration"
        class="text-[color:var(--accent-amber)]"
      >
        У части фаз не задана длительность
      </span>
    </div>

    <div
      class="flex h-9 w-full overflow-hidden rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
      data-testid="recipe-phase-timeline"
    >
      <button
        v-for="segment in segments"
        :key="segment.key"
        type="button"
        class="group relative flex min-w-0 items-center justify-center border-r border-[color:var(--bg-main)] px-1 text-[10px] font-semibold transition-opacity last:border-r-0 hover:opacity-100"
        :class="isActive(segment.key) ? 'opacity-100 ring-1 ring-inset ring-[color:var(--text-primary)]' : 'opacity-80'"
        :style="{ width: `${segment.widthPct}%`, background: segment.background, color: 'var(--bg-main)' }"
        :title="`${segment.label} · ${segment.durationLabel} · ${segment.dayRange}`"
        @click="$emit('select', segment.key)"
      >
        <span class="truncate">{{ segment.shortLabel }}</span>
      </button>
    </div>

    <div class="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[color:var(--text-muted)]">
      <span
        v-for="segment in segments"
        :key="`legend-${segment.key}`"
        class="flex items-center gap-1.5"
      >
        <span
          class="inline-block h-2 w-2 rounded-sm"
          :style="{ background: segment.background }"
        ></span>
        <span class="text-[color:var(--text-primary)]">{{ segment.label }}</span>
        <span>{{ segment.durationLabel }} · {{ segment.dayRange }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  formatDayRange,
  formatDurationHours,
  phaseColor,
  type RecipePhaseVisual,
} from '@/utils/recipeVisualization'

const props = withDefaults(
  defineProps<{
    phases: RecipePhaseVisual[]
    activeKey?: string | null
  }>(),
  { activeKey: null },
)

defineEmits<{ select: [key: string] }>()

const MIN_SEGMENT_WIDTH_PCT = 4

const totalHours = computed(() =>
  props.phases.reduce((sum, phase) => sum + (phase.durationHours ?? 0), 0),
)

const hasUnknownDuration = computed(() => props.phases.some((phase) => phase.durationHours === null))

const totalLabel = computed(() => formatDurationHours(totalHours.value || null))

const segments = computed(() => {
  const total = totalHours.value
  const rawWidths = props.phases.map((phase) => {
    if (total <= 0) {
      return 100 / Math.max(props.phases.length, 1)
    }

    return Math.max(((phase.durationHours ?? 0) / total) * 100, MIN_SEGMENT_WIDTH_PCT)
  })
  const widthSum = rawWidths.reduce((sum, width) => sum + width, 0) || 1

  return props.phases.map((phase, index) => ({
    key: phase.key,
    label: `${phase.position + 1}. ${phase.name}`,
    shortLabel: phase.name,
    background: phaseColor(phase.position),
    widthPct: (rawWidths[index] / widthSum) * 100,
    durationLabel: formatDurationHours(phase.durationHours),
    dayRange: formatDayRange(phase),
  }))
})

function isActive(key: string): boolean {
  return props.activeKey === key
}
</script>
