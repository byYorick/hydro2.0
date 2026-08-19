<template>
  <figure class="space-y-1">
    <figcaption class="flex items-baseline justify-between gap-2">
      <span class="text-xs font-semibold text-[color:var(--text-primary)]">{{ config.label }}</span>
      <span class="text-[10px] text-[color:var(--text-dim)]">{{ config.unit || '' }}</span>
    </figcaption>

    <svg
      v-if="hasData"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="h-auto w-full"
      role="img"
      :aria-label="`График ${config.label} по фазам рецепта`"
      :data-testid="`recipe-chart-${metric}`"
    >
      <g>
        <line
          v-for="tick in yTicks"
          :key="`grid-${tick.value}`"
          :x1="PADDING.left"
          :x2="WIDTH - PADDING.right"
          :y1="tick.y"
          :y2="tick.y"
          stroke="var(--border-muted)"
          stroke-width="0.5"
        />
        <text
          v-for="tick in yTicks"
          :key="`label-${tick.value}`"
          :x="PADDING.left - 4"
          :y="tick.y + 3"
          text-anchor="end"
          font-size="8"
          fill="var(--text-dim)"
        >
          {{ tick.label }}
        </text>
      </g>

      <g>
        <rect
          v-for="band in bands"
          :key="`band-${band.key}`"
          :x="band.x"
          :y="band.y"
          :width="band.width"
          :height="band.height"
          :fill="config.color"
          fill-opacity="0.18"
        />
      </g>

      <polyline
        v-if="targetPoints.length > 0"
        :points="targetPolyline"
        fill="none"
        :stroke="config.color"
        stroke-width="1.6"
        stroke-linejoin="round"
      />

      <g>
        <line
          v-for="separator in separators"
          :key="`sep-${separator.key}`"
          :x1="separator.x"
          :x2="separator.x"
          :y1="PADDING.top"
          :y2="HEIGHT - PADDING.bottom"
          stroke="var(--border-muted)"
          stroke-width="0.5"
          stroke-dasharray="2 2"
        />
      </g>

      <g>
        <text
          v-for="label in phaseLabels"
          :key="`phase-${label.key}`"
          :x="label.x"
          :y="HEIGHT - PADDING.bottom + 10"
          text-anchor="middle"
          font-size="7.5"
          fill="var(--text-dim)"
        >
          {{ label.text }}
        </text>
      </g>
    </svg>

    <p
      v-else
      class="rounded-md border border-dashed border-[color:var(--border-muted)] px-3 py-4 text-center text-xs text-[color:var(--text-dim)]"
    >
      Нет данных по параметру
    </p>
  </figure>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RecipeChartMetric, RecipePhaseVisual, VisualRange } from '@/utils/recipeVisualization'
import { formatNumberValue } from '@/utils/recipeVisualization'

const props = defineProps<{
  phases: RecipePhaseVisual[]
  metric: RecipeChartMetric
}>()

const WIDTH = 640
const HEIGHT = 190
const PADDING = { left: 38, right: 10, top: 12, bottom: 26 }

interface MetricConfig {
  label: string
  unit: string
  color: string
  digits: number
  read: (phase: RecipePhaseVisual) => VisualRange
}

const METRICS: Record<RecipeChartMetric, MetricConfig> = {
  ph: {
    label: 'pH раствора',
    unit: '',
    color: 'var(--accent-cyan)',
    digits: 2,
    read: (phase) => phase.ph,
  },
  ec: {
    label: 'EC раствора',
    unit: 'mS/cm',
    color: 'var(--accent-green)',
    digits: 2,
    read: (phase) => phase.ec,
  },
  temperature: {
    label: 'Температура воздуха',
    unit: '°C',
    color: 'var(--accent-amber)',
    digits: 1,
    read: (phase) => phase.temperature,
  },
  humidity: {
    label: 'Влажность воздуха',
    unit: '%',
    color: 'var(--accent-cyan)',
    digits: 0,
    read: (phase) => phase.humidity,
  },
  co2: {
    label: 'CO₂',
    unit: 'ppm',
    color: 'var(--accent-lime)',
    digits: 0,
    read: (phase) => phase.co2,
  },
  dli: {
    label: 'DLI',
    unit: 'моль/м²·сут',
    color: 'var(--accent-lime)',
    digits: 1,
    read: (phase) => phase.dli,
  },
  light: {
    label: 'Фотопериод',
    unit: 'ч',
    color: 'var(--accent-amber)',
    digits: 0,
    read: (phase) => ({ target: phase.lightHours, min: null, max: null }),
  },
  solutionTemp: {
    label: 'Температура раствора',
    unit: '°C',
    color: 'var(--accent-cyan)',
    digits: 1,
    read: (phase) => phase.solutionTemp,
  },
}

const config = computed(() => METRICS[props.metric])

interface PhaseSlot {
  key: string
  index: number
  name: string
  x0: number
  x1: number
  range: VisualRange
}

const slots = computed<PhaseSlot[]>(() => {
  const phases = props.phases
  if (phases.length === 0) {
    return []
  }

  const totalHours = phases.reduce((sum, phase) => sum + (phase.durationHours ?? 0), 0)
  const innerWidth = WIDTH - PADDING.left - PADDING.right
  const useEqualWidth = totalHours <= 0
  let cursor = PADDING.left

  return phases.map((phase, position) => {
    const share = useEqualWidth
      ? 1 / phases.length
      : (phase.durationHours ?? 0) / totalHours
    const width = Math.max(share * innerWidth, innerWidth * 0.02)
    const x0 = cursor
    cursor += width

    return {
      key: phase.key,
      index: position,
      name: phase.name,
      x0,
      x1: Math.min(cursor, WIDTH - PADDING.right),
      range: config.value.read(phase),
    }
  })
})

const values = computed(() =>
  slots.value.flatMap((slot) => [slot.range.min, slot.range.max, slot.range.target])
    .filter((value): value is number => value !== null),
)

const hasData = computed(() => values.value.length > 0)

const domain = computed(() => {
  if (!hasData.value) {
    return { min: 0, max: 1 }
  }

  const min = Math.min(...values.value)
  const max = Math.max(...values.value)
  if (min === max) {
    const pad = Math.abs(min) > 0 ? Math.abs(min) * 0.1 : 1
    return { min: min - pad, max: max + pad }
  }

  const pad = (max - min) * 0.15
  return { min: min - pad, max: max + pad }
})

function scaleY(value: number): number {
  const { min, max } = domain.value
  const ratio = (value - min) / (max - min || 1)
  return HEIGHT - PADDING.bottom - ratio * (HEIGHT - PADDING.top - PADDING.bottom)
}

const yTicks = computed(() => {
  const { min, max } = domain.value
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, step) => {
    const value = min + ((max - min) / steps) * step
    return {
      value,
      y: scaleY(value),
      label: formatNumberValue(value, config.value.digits),
    }
  })
})

const bands = computed(() =>
  slots.value
    .map((slot) => {
      const min = slot.range.min ?? slot.range.target
      const max = slot.range.max ?? slot.range.target
      if (min === null || max === null || min === max) {
        return null
      }

      const yTop = scaleY(max)
      const yBottom = scaleY(min)
      return {
        key: slot.key,
        x: slot.x0,
        y: yTop,
        width: Math.max(slot.x1 - slot.x0, 1),
        height: Math.max(yBottom - yTop, 1),
      }
    })
    .filter((band): band is NonNullable<typeof band> => band !== null),
)

const targetPoints = computed(() =>
  slots.value.flatMap((slot) => {
    const min = slot.range.min
    const max = slot.range.max
    const fallback = min !== null && max !== null ? (min + max) / 2 : min ?? max
    const value = slot.range.target ?? fallback
    if (value === null) {
      return []
    }

    const y = scaleY(value)
    return [
      { x: slot.x0, y },
      { x: slot.x1, y },
    ]
  }),
)

const targetPolyline = computed(() =>
  targetPoints.value.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' '),
)

const separators = computed(() =>
  slots.value.slice(1).map((slot) => ({ key: slot.key, x: slot.x0 })),
)

const phaseLabels = computed(() =>
  slots.value.map((slot) => ({
    key: slot.key,
    x: (slot.x0 + slot.x1) / 2,
    text: slot.x1 - slot.x0 < 40 ? String(slot.index + 1) : slot.name,
  })),
)
</script>
