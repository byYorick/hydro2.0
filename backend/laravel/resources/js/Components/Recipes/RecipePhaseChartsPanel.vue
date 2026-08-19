<template>
  <div
    v-if="availableMetrics.length > 0"
    class="space-y-3"
    data-testid="recipe-charts-panel"
  >
    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="metric in availableMetrics"
        :key="metric"
        type="button"
        class="rounded-md border px-2 py-1 text-[11px] transition-colors"
        :class="isSelected(metric)
          ? 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
          : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]'"
        @click="toggle(metric)"
      >
        {{ METRIC_LABELS[metric] }}
      </button>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <RecipeParameterChart
        v-for="metric in selectedMetrics"
        :key="metric"
        :phases="phases"
        :metric="metric"
      />
    </div>
  </div>
  <p
    v-else
    class="text-xs text-[color:var(--text-dim)]"
  >
    Нет числовых параметров для построения графиков
  </p>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RecipeParameterChart from '@/Components/Recipes/RecipeParameterChart.vue'
import { rangeHasValue, type RecipeChartMetric, type RecipePhaseVisual } from '@/utils/recipeVisualization'

const props = withDefaults(
  defineProps<{
    phases: RecipePhaseVisual[]
    defaultMetrics?: RecipeChartMetric[]
  }>(),
  { defaultMetrics: () => ['ph', 'ec', 'temperature', 'humidity'] },
)

const METRIC_LABELS: Record<RecipeChartMetric, string> = {
  ph: 'pH',
  ec: 'EC',
  temperature: 'Температура',
  humidity: 'Влажность',
  light: 'Фотопериод',
  co2: 'CO₂',
  dli: 'DLI',
  solutionTemp: 'Раствор',
}

const METRIC_ORDER: RecipeChartMetric[] = ['ph', 'ec', 'temperature', 'humidity', 'light', 'co2', 'dli', 'solutionTemp']

const availableMetrics = computed<RecipeChartMetric[]>(() =>
  METRIC_ORDER.filter((metric) => props.phases.some((phase) => metricHasData(phase, metric))),
)

const selected = ref<RecipeChartMetric[]>([])

watch(
  availableMetrics,
  (metrics) => {
    const preferred = props.defaultMetrics.filter((metric) => metrics.includes(metric))
    selected.value = preferred.length > 0 ? preferred : metrics.slice(0, 2)
  },
  { immediate: true },
)

const selectedMetrics = computed(() =>
  METRIC_ORDER.filter((metric) => selected.value.includes(metric) && availableMetrics.value.includes(metric)),
)

function metricHasData(phase: RecipePhaseVisual, metric: RecipeChartMetric): boolean {
  switch (metric) {
    case 'ph':
      return rangeHasValue(phase.ph)
    case 'ec':
      return rangeHasValue(phase.ec)
    case 'temperature':
      return rangeHasValue(phase.temperature)
    case 'humidity':
      return rangeHasValue(phase.humidity)
    case 'co2':
      return rangeHasValue(phase.co2)
    case 'dli':
      return rangeHasValue(phase.dli)
    case 'solutionTemp':
      return rangeHasValue(phase.solutionTemp)
    case 'light':
      return phase.lightHours !== null
    default:
      return false
  }
}

function isSelected(metric: RecipeChartMetric): boolean {
  return selected.value.includes(metric)
}

function toggle(metric: RecipeChartMetric): void {
  if (selected.value.includes(metric)) {
    if (selected.value.length === 1) {
      return
    }

    selected.value = selected.value.filter((item) => item !== metric)
    return
  }

  selected.value = [...selected.value, metric]
}
</script>
