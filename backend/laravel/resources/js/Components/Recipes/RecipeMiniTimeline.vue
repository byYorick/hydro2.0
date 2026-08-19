<template>
  <div
    v-if="segments.length > 0"
    class="flex h-1.5 w-full min-w-[80px] overflow-hidden rounded-full bg-[color:var(--bg-elevated)]"
    :title="tooltip"
    data-testid="recipe-mini-timeline"
  >
    <span
      v-for="segment in segments"
      :key="segment.key"
      class="h-full"
      :style="{ width: `${segment.widthPct}%`, background: segment.color }"
    ></span>
  </div>
  <span
    v-else
    class="text-[color:var(--text-dim)]"
  >—</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RecipePhasePreview } from '@/types'
import { formatDurationHours, phaseColor } from '@/utils/recipeVisualization'

const props = withDefaults(
  defineProps<{ phases?: RecipePhasePreview[] | null }>(),
  { phases: () => [] },
)

const sorted = computed(() =>
  [...(props.phases ?? [])].sort((a, b) => (a.phase_index ?? 0) - (b.phase_index ?? 0)),
)

const totalHours = computed(() =>
  sorted.value.reduce((sum, phase) => sum + (phase.duration_hours ?? 0), 0),
)

const segments = computed(() => {
  const phases = sorted.value
  if (phases.length === 0) {
    return []
  }

  const total = totalHours.value
  return phases.map((phase, index) => ({
    key: `${phase.phase_index}-${index}`,
    color: phaseColor(index),
    widthPct: total > 0 ? ((phase.duration_hours ?? 0) / total) * 100 : 100 / phases.length,
  }))
})

const tooltip = computed(() =>
  sorted.value
    .map((phase, index) => `${index + 1}. ${phase.name || 'Фаза'} — ${formatDurationHours(phase.duration_hours ?? null)}`)
    .join('\n'),
)
</script>
