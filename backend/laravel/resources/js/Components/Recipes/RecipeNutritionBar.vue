<template>
  <div
    class="space-y-2"
    data-testid="recipe-nutrition-bar"
  >
    <div
      v-if="segments.length > 0"
      class="flex h-3 w-full overflow-hidden rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
    >
      <span
        v-for="segment in segments"
        :key="segment.key"
        class="h-full"
        :style="{ width: `${segment.widthPct}%`, background: segment.color }"
        :title="`${segment.label}: ${segment.ratioLabel}`"
      ></span>
    </div>

    <div class="grid gap-1 text-[11px] sm:grid-cols-2">
      <div
        v-for="component in visibleComponents"
        :key="component.key"
        class="flex items-center gap-1.5"
      >
        <span
          class="inline-block h-2 w-2 shrink-0 rounded-sm"
          :style="{ background: colorOf(component.key) }"
        ></span>
        <span class="text-[color:var(--text-primary)]">{{ component.label }}</span>
        <span class="font-mono text-[color:var(--text-muted)]">
          {{ formatNumberValue(component.ratioPct, 1) }}%
        </span>
        <span
          v-if="component.doseMlL !== null"
          class="font-mono text-[color:var(--text-dim)]"
        >
          · {{ formatNumberValue(component.doseMlL, 2) }} мл/л
        </span>
        <span class="truncate text-[color:var(--text-dim)]">· {{ productLabel(component) }}</span>
      </div>
    </div>

    <div class="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[color:var(--text-dim)]">
      <span>Сумма долей: <span :class="ratioSumClass">{{ formatNumberValue(nutrition.ratioSum, 1) }}%</span></span>
      <span v-if="nutrition.programCode">Программа: {{ nutrition.programCode }}</span>
      <span>Режим: {{ nutrientModeLabel(nutrition.mode) }}</span>
      <span v-if="nutrition.ecDosingMode">Дозирование: {{ dosingLabel }}</span>
      <span v-if="nutrition.solutionVolumeL !== null">Объём: {{ formatNumberValue(nutrition.solutionVolumeL, 1) }} л</span>
      <span v-if="nutrition.doseDelaySec !== null">Пауза доз: {{ formatNumberValue(nutrition.doseDelaySec, 0) }} с</span>
      <span v-if="nutrition.ecStopTolerance !== null">EC stop tolerance: {{ formatNumberValue(nutrition.ecStopTolerance, 3) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  NUTRITION_COLORS,
  formatNumberValue,
  nutrientModeLabel,
  productLabel,
  type VisualNutrition,
  type VisualNutritionComponent,
} from '@/utils/recipeVisualization'

const props = defineProps<{ nutrition: VisualNutrition }>()

const visibleComponents = computed(() =>
  props.nutrition.components.filter(
    (component) => component.ratioPct !== null || component.doseMlL !== null || component.productId !== null,
  ),
)

const segments = computed(() => {
  const total = props.nutrition.components.reduce((sum, item) => sum + (item.ratioPct ?? 0), 0)
  if (total <= 0) {
    return []
  }

  return props.nutrition.components
    .filter((component) => (component.ratioPct ?? 0) > 0)
    .map((component) => ({
      key: component.key,
      label: component.label,
      color: NUTRITION_COLORS[component.key],
      widthPct: ((component.ratioPct ?? 0) / total) * 100,
      ratioLabel: `${formatNumberValue(component.ratioPct, 1)}%`,
    }))
})

const ratioSumClass = computed(() =>
  Math.abs(props.nutrition.ratioSum - 100) <= 0.01
    ? 'text-[color:var(--accent-green)] font-semibold'
    : 'text-[color:var(--accent-amber)] font-semibold',
)

const dosingLabel = computed(() =>
  props.nutrition.ecDosingMode === 'parallel' ? 'параллельное' : 'последовательное',
)

function colorOf(key: VisualNutritionComponent['key']): string {
  return NUTRITION_COLORS[key]
}
</script>
