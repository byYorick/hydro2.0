<template>
  <Card class="relative">
    <div class="flex items-center justify-between mb-2">
      <div class="text-sm font-semibold">
        {{ title }}
      </div>
      <div class="flex items-center gap-2">
        <div class="text-xs text-[color:var(--text-dim)] hidden sm:inline">
          <span class="mr-2">🖱️ Колесо мыши — zoom</span>
          <span>Перетаскивание — pan</span>
        </div>
      </div>
    </div>
    
    <!-- Легенда -->
    <div class="flex items-center gap-4 mb-2 text-xs">
      <div
        v-for="seriesItem in seriesConfig"
        :key="seriesItem.name"
        class="flex items-center gap-2"
      >
        <div
          class="w-3 h-0.5 rounded"
          :style="{ backgroundColor: seriesItem.color }"
        ></div>
        <span class="text-[color:var(--text-muted)]">{{ seriesItem.label }}</span>
        <span
          v-if="seriesItem.currentValue !== null && seriesItem.currentValue !== undefined"
          class="font-medium"
          :style="{ color: seriesItem.color }"
        >
          {{ formatValue(seriesItem.currentValue, seriesItem.name) }}
        </span>
      </div>
    </div>
    
    <ChartBase
      :option="option"
      :dark="isDark"
    />
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import ChartBase from '@/Components/ChartBase.vue'
import type { TelemetrySample } from '@/types'
import { useTheme } from '@/composables/useTheme'
import { useChartColors } from '@/composables/useChartColors'
import { useTelemetryChartOptions } from '@/composables/useTelemetryChartOptions'
import type { TelemetryRange } from '@/types'

interface SeriesConfig {
  name: string
  label: string
  color: string
  data: TelemetrySample[]
  currentValue?: number | null
  yAxisIndex?: number
  targetRange?: {
    min?: number
    max?: number
  }
}

interface Props {
  title?: string
  series: SeriesConfig[]
  timeRange?: TelemetryRange
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Телеметрия',
  series: () => [],
  timeRange: '24H',
})

const { theme, isDark } = useTheme()
const { palette } = useChartColors(theme)

const seriesConfig = computed(() => props.series)

// Утилита для форматирования значения в легенде
const formatValue = (value: number | null | undefined, seriesName: string): string => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) {
    return '—'
  }
  const isPH = seriesName.toLowerCase().includes('ph')
  return value.toFixed(isPH ? 2 : 1)
}
const timeRange = computed<TelemetryRange>(() => props.timeRange ?? '24H')
const { option } = useTelemetryChartOptions(palette, seriesConfig, timeRange)
</script>
