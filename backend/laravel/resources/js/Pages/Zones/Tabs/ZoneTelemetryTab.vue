<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Диапазон</span>
          <button
            v-for="range in ranges"
            :key="range"
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="range === chartTimeRange
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="onRangeClick(range)"
          >
            {{ range }}
          </button>
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="showSeparateCharts
              ? 'border-[color:var(--accent-amber)] text-[color:var(--accent-amber)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="showSeparateCharts = !showSeparateCharts"
          >
            Раздельные графики
          </button>
        </div>
        <div class="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            @click="exportTelemetry"
          >
            Экспорт CSV
          </Button>
        </div>
      </div>
    </section>

    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="mb-3">
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Графики телеметрии
        </div>
        <div class="text-xs text-[color:var(--text-muted)] mt-1">
          pH и EC
        </div>
      </div>

      <div v-if="chartDataPh.length > 0 || chartDataEc.length > 0">
        <MultiSeriesTelemetryChart
          v-if="!showSeparateCharts"
          title="pH и EC"
          :series="multiSeriesData"
          :time-range="chartTimeRange"
          @time-range-change="onChartRangeChange"
        />
        <div
          v-else
          class="space-y-3"
        >
          <ZoneTelemetryChart
            title="pH"
            :data="chartDataPh"
            series-name="pH"
            :time-range="chartTimeRange"
            @time-range-change="onChartRangeChange"
          />
          <ZoneTelemetryChart
            title="EC"
            :data="chartDataEc"
            series-name="EC"
            :time-range="chartTimeRange"
            @time-range-change="onChartRangeChange"
          />
        </div>
      </div>
      <div
        v-else
        class="text-center py-6"
      >
        <div class="text-4xl mb-2">
          📊
        </div>
        <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
          Нет данных для графиков
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          Данные телеметрии появятся после начала работы датчиков в зоне
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import Button from '@/Components/Button.vue'
import { useTheme } from '@/composables/useTheme'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))
const MultiSeriesTelemetryChart = defineAsyncComponent(() => import('@/Components/MultiSeriesTelemetryChart.vue'))

type TelemetryRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

interface Props {
  zoneId: number | null
  chartTimeRange: TelemetryRange
  chartDataPh: Array<{ ts: number; value: number }>
  chartDataEc: Array<{ ts: number; value: number }>
  telemetry: ZoneTelemetry
  targets: ZoneTargetsType
}

const props = defineProps<Props>()

const emit = defineEmits<{ (e: 'timeRangeChange', range: TelemetryRange): void }>()

const ranges: TelemetryRange[] = ['1H', '24H', '7D', '30D', 'ALL']
const showSeparateCharts = ref(false)

const { theme } = useTheme()
const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return {
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
  }
})

const multiSeriesData = computed(() => {
  return [
    {
      name: 'ph',
      label: 'pH',
      color: chartPalette.value.ph,
      data: props.chartDataPh,
      currentValue: props.telemetry?.ph ?? null,
      yAxisIndex: 0,
      targetRange: (props.targets?.ph && typeof props.targets.ph === 'object' && 'min' in props.targets.ph) ? {
        min: props.targets.ph.min,
        max: props.targets.ph.max,
      } : undefined,
    },
    {
      name: 'ec',
      label: 'EC',
      color: chartPalette.value.ec,
      data: props.chartDataEc,
      currentValue: props.telemetry?.ec ?? null,
      yAxisIndex: 1,
      targetRange: (props.targets?.ec && typeof props.targets.ec === 'object' && 'min' in props.targets.ec) ? {
        min: props.targets.ec.min,
        max: props.targets.ec.max,
      } : undefined,
    },
  ]
})

const onRangeClick = (range: TelemetryRange): void => {
  emit('timeRangeChange', range)
}

const onChartRangeChange = (range: string): void => {
  emit('timeRangeChange', range as TelemetryRange)
}

const exportTelemetry = (): void => {
  if (typeof window === 'undefined') return

  const rows: string[] = ['metric,timestamp,value']
  props.chartDataPh.forEach((point) => {
    rows.push(`PH,${new Date(point.ts).toISOString()},${point.value}`)
  })
  props.chartDataEc.forEach((point) => {
    rows.push(`EC,${new Date(point.ts).toISOString()},${point.value}`)
  })

  const csv = rows.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const fileLabel = props.zoneId ? `zone-${props.zoneId}` : 'zone'
  link.href = url
  link.download = `${fileLabel}-telemetry-${props.chartTimeRange}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>
