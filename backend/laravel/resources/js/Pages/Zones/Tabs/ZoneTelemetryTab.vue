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

    <section
      v-if="hasSoilMoisture"
      class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4"
    >
      <div class="mb-3">
        <div class="flex items-center gap-2">
          <div class="text-sm font-semibold text-[color:var(--text-primary)]">
            Влажность почвы
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)] text-[color:var(--accent-amber)] font-medium">
            Умный полив
          </span>
        </div>
        <div class="text-xs text-[color:var(--text-muted)] mt-1">
          {{ soilMoistureNodeNames.length > 1 ? `${soilMoistureNodeNames.length} датчика` : 'Датчик влажности субстрата' }}
        </div>
      </div>

      <div v-if="soilMoistureSeries.length > 0 && hasSoilMoistureData">
        <MultiSeriesTelemetryChart
          title="Влажность почвы, %"
          :series="soilMoistureSeries"
          :time-range="chartTimeRange"
          @time-range-change="onChartRangeChange"
        />
      </div>
      <div
        v-else
        class="text-center py-6"
      >
        <div class="text-3xl mb-2">
          💧
        </div>
        <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
          Нет данных влажности почвы
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          Данные появятся после того, как датчики влажности начнут отправлять телеметрию
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
import type { Device } from '@/types/Device'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))
const MultiSeriesTelemetryChart = defineAsyncComponent(() => import('@/Components/MultiSeriesTelemetryChart.vue'))

type TelemetryRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

type PhaseTargets = {
  ph?: { min?: number; max?: number } | null
  ec?: { min?: number; max?: number } | null
}

type ZoneTargetsInput = ZoneTargetsType | PhaseTargets

type TargetRange = {
  min: number
  max: number
}


interface Props {
  zoneId: number | null
  chartTimeRange: TelemetryRange
  chartDataPh: Array<{ ts: number; value: number }>
  chartDataEc: Array<{ ts: number; value: number }>
  chartDataSoilMoisture: Record<number, Array<{ ts: number; value: number }>>
  hasSoilMoisture: boolean
  devices: Device[]
  telemetry: ZoneTelemetry
  targets: ZoneTargetsInput
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

const SOIL_MOISTURE_COLORS = [
  { cssVar: '--accent-amber', fallback: '#f59e0b' },
  { cssVar: '--accent-orange', fallback: '#f97316' },
  { cssVar: '--accent-purple', fallback: '#a855f7' },
  { cssVar: '--accent-pink', fallback: '#ec4899' },
  { cssVar: '--accent-teal', fallback: '#14b8a6' },
]

const chartPalette = computed(() => {
  theme.value
  return {
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
  }
})

const isPhaseTargets = (targets: ZoneTargetsInput): targets is PhaseTargets => {
  return typeof targets === 'object' && targets !== null && ('ph' in targets || 'ec' in targets)
}

const resolveTargetRange = (metric: 'ph' | 'ec'): TargetRange | undefined => {
  const targets = props.targets
  if (!targets || typeof targets !== 'object') return undefined

  if (isPhaseTargets(targets)) {
    const phaseTarget = targets[metric]
    if (phaseTarget && typeof phaseTarget === 'object') {
      const min = phaseTarget.min
      const max = phaseTarget.max
      if (min !== undefined && max !== undefined) {
        return { min, max }
      }
    }
  }

  const legacyTargets = targets as ZoneTargetsType
  if (metric === 'ph' && legacyTargets.ph_min !== undefined && legacyTargets.ph_max !== undefined) {
    return { min: legacyTargets.ph_min, max: legacyTargets.ph_max }
  }
  if (metric === 'ec' && legacyTargets.ec_min !== undefined && legacyTargets.ec_max !== undefined) {
    return { min: legacyTargets.ec_min, max: legacyTargets.ec_max }
  }

  return undefined
}

const multiSeriesData = computed(() => {
  return [
    {
      name: 'ph',
      label: 'pH',
      color: chartPalette.value.ph,
      data: props.chartDataPh,
      currentValue: props.telemetry?.ph ?? null,
      yAxisIndex: 0,
      targetRange: resolveTargetRange('ph'),
    },
    {
      name: 'ec',
      label: 'EC',
      color: chartPalette.value.ec,
      data: props.chartDataEc,
      currentValue: props.telemetry?.ec ?? null,
      yAxisIndex: 1,
      targetRange: resolveTargetRange('ec'),
    },
  ]
})

const nodeNameById = computed((): Record<number, string> => {
  const map: Record<number, string> = {}
  for (const device of props.devices) {
    map[device.id] = device.name || `Нода #${device.id}`
  }
  return map
})

const soilMoistureNodeIds = computed((): number[] => {
  return Object.keys(props.chartDataSoilMoisture).map(Number).filter((id) => id > 0)
})

const soilMoistureNodeNames = computed((): string[] => {
  return soilMoistureNodeIds.value.map(
    (id) => nodeNameById.value[id] ?? `Нода #${id}`
  )
})

const hasSoilMoistureData = computed((): boolean => {
  return soilMoistureNodeIds.value.some(
    (id) => (props.chartDataSoilMoisture[id]?.length ?? 0) > 0
  )
})

const soilMoistureSeries = computed(() => {
  theme.value
  return soilMoistureNodeIds.value.map((nodeId, index) => {
    const colorDef = SOIL_MOISTURE_COLORS[index % SOIL_MOISTURE_COLORS.length]
    const color = resolveCssColor(colorDef.cssVar, colorDef.fallback)
    const nodeName = nodeNameById.value[nodeId] ?? `Нода #${nodeId}`
    return {
      name: `soil_${nodeId}`,
      label: nodeName,
      color,
      data: props.chartDataSoilMoisture[nodeId] ?? [],
      currentValue: null,
      yAxisIndex: 0,
    }
  })
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
