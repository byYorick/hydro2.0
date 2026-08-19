<template>
  <dl
    class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6"
    data-testid="recipe-summary-stats"
  >
    <div
      v-for="stat in stats"
      :key="stat.key"
      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2"
    >
      <dt class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
        {{ stat.label }}
      </dt>
      <dd class="mt-0.5 text-sm font-semibold text-[color:var(--text-primary)]">
        {{ stat.value }}
      </dd>
      <dd
        v-if="stat.hint"
        class="text-[10px] text-[color:var(--text-dim)]"
      >
        {{ stat.hint }}
      </dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  formatDurationHours,
  formatNumberValue,
  formatRangeValue,
  type RecipeVisualSummary,
} from '@/utils/recipeVisualization'

const props = withDefaults(
  defineProps<{
    summary: RecipeVisualSummary
    cropLabel?: string | null
    statusLabel?: string | null
    activeZones?: number | null
  }>(),
  { cropLabel: null, statusLabel: null, activeZones: null },
)

interface Stat {
  key: string
  label: string
  value: string
  hint?: string
}

const stats = computed<Stat[]>(() => {
  const summary = props.summary
  const items: Stat[] = [
    {
      key: 'duration',
      label: 'Длительность',
      value: formatDurationHours(summary.totalHours),
      hint: summary.totalHours === null ? undefined : `${formatNumberValue(summary.totalHours, 0)} ч`,
    },
    {
      key: 'phases',
      label: 'Фаз',
      value: String(summary.phaseCount),
    },
    {
      key: 'ph',
      label: 'pH',
      value: formatRangeValue(summary.ph, '', 2),
    },
    {
      key: 'ec',
      label: 'EC',
      value: formatRangeValue(summary.ec, 'mS/cm', 2),
    },
    {
      key: 'temperature',
      label: 'Температура',
      value: formatRangeValue(summary.temperature, '°C', 1),
    },
    {
      key: 'humidity',
      label: 'Влажность',
      value: formatRangeValue(summary.humidity, '%', 0),
    },
  ]

  if (props.cropLabel) {
    items.push({ key: 'crop', label: 'Культура', value: props.cropLabel })
  }

  if (props.statusLabel) {
    items.push({ key: 'status', label: 'Статус', value: props.statusLabel })
  }

  if (props.activeZones !== null) {
    items.push({ key: 'zones', label: 'Зон в работе', value: String(props.activeZones) })
  }

  return items
})
</script>
