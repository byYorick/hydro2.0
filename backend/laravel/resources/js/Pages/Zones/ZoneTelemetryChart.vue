<template>
  <Card class="relative">
    <div class="mb-2">
      <div class="text-sm font-semibold">
        {{ title }}
      </div>
      <div class="text-xs text-[color:var(--text-dim)] hidden sm:inline">
        <span class="mr-2">🖱️ Колесо мыши — zoom</span>
        <span>Перетаскивание — pan</span>
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

interface Props {
  title: string
  seriesName?: string
  data?: TelemetrySample[]
  timeRange?: TelemetryRange
  currentValue?: number | null
  targetRange?: { min: number; max: number } | null
}

const props = withDefaults(defineProps<Props>(), {
  seriesName: 'value',
  data: () => [],
  timeRange: '24H',
  currentValue: null,
  targetRange: null,
})

const { theme, isDark } = useTheme()
const { palette } = useChartColors(theme)

const series = computed(() => [{
  name: props.seriesName,
  label: props.seriesName,
  color: '#60a5fa',
  data: props.data,
  yAxisIndex: 0,
  currentValue: props.currentValue,
  targetRange: props.targetRange,
}])

const timeRange = computed<TelemetryRange>(() => props.timeRange)
const { option } = useTelemetryChartOptions(palette, series, timeRange)
</script>
