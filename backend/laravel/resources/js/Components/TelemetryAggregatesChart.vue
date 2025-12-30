<template>
  <div
    class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4"
    :data-testid="testId"
  >
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          {{ title }}
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          {{ subtitle }}
        </div>
      </div>
      <div class="text-xs text-[color:var(--text-dim)]">
        {{ meta }}
      </div>
    </div>

    <div v-if="loading" class="py-4">
      <SkeletonBlock :lines="4" line-height="0.75rem" />
    </div>
    <div v-else-if="error" class="text-sm text-[color:var(--accent-red)] py-6 text-center">
      {{ error }}
    </div>
    <div v-else-if="data.length === 0" class="py-6">
      <EmptyState
        title="Нет данных для отображения"
        description="Попробуйте выбрать другой диапазон или дождитесь новых измерений."
        container-class="py-0"
      />
    </div>
    <div v-else class="h-[320px]">
      <ChartBase :option="option" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ChartBase from '@/Components/ChartBase.vue'
import EmptyState from '@/Components/EmptyState.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
import { useTheme } from '@/composables/useTheme'
import type { EChartsOption } from 'echarts'

interface AggregatePoint {
  ts: string
  avg: number
  min: number
  max: number
  median?: number
}

interface Props {
  data: AggregatePoint[]
  loading?: boolean
  error?: string | null
  metric?: string
  period?: string
  showMedian?: boolean
  testId?: string
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  loading: false,
  error: null,
  metric: '',
  period: '',
  showMedian: false,
  testId: undefined,
})

const title = computed(() => `Агрегаты телеметрии${props.metric ? ` · ${props.metric}` : ''}`)
const subtitle = computed(() => (props.period ? `Период: ${props.period}` : ''))
const meta = computed(() => (props.data.length ? `${props.data.length} точек` : ''))

const { theme } = useTheme()

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const colors = computed(() => {
  theme.value
  return {
    avg: resolveCssColor('--accent-cyan', '#60a5fa'),
    band: resolveCssColor('--accent-green', '#22c55e'),
    median: resolveCssColor('--accent-amber', '#f59e0b'),
    textPrimary: resolveCssColor('--text-primary', '#111827'),
    textDim: resolveCssColor('--text-dim', '#6b7280'),
    borderMuted: resolveCssColor('--border-muted', '#e5e7eb'),
    tooltipBg: resolveCssColor('--bg-surface-strong', '#111827'),
  }
})

const formatValue = (value: number): string => {
  if (Number.isNaN(value) || !isFinite(value)) return '—'
  const metric = props.metric?.toUpperCase() || ''
  const decimals = metric === 'PH' ? 2 : 1
  return value.toFixed(decimals)
}

const toTimestamp = (ts: string): number => {
  const value = new Date(ts).getTime()
  return Number.isNaN(value) ? 0 : value
}

const option = computed<EChartsOption>(() => {
  const points = props.data.map((point) => ({
    ts: toTimestamp(point.ts),
    avg: point.avg,
    min: point.min,
    max: point.max,
    median: point.median ?? point.avg,
  }))

  const minSeries = points.map((p) => [p.ts, p.min])
  const bandSeries = points.map((p) => [p.ts, Math.max(0, p.max - p.min)])
  const avgSeries = points.map((p) => [p.ts, p.avg])
  const medianSeries = points.map((p) => [p.ts, p.median ?? p.avg])

  const showMedian = props.showMedian

  return {
    grid: { left: 50, right: 24, top: 20, bottom: 40, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.value.tooltipBg,
      borderColor: colors.value.borderMuted,
      textStyle: { color: colors.value.textPrimary, fontSize: 12 },
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const time = new Date(params[0].value[0]).toLocaleString('ru-RU')
        const lines = [`${time}`]
        params.forEach((item: any) => {
          if (item.seriesName === 'band-min' || item.seriesName === 'band-range') return
          lines.push(`${item.marker}${item.seriesName}: ${formatValue(item.value[1])}`)
        })
        const minPoint = points[params[0].dataIndex]
        if (minPoint) {
          lines.push(`min: ${formatValue(minPoint.min)} / max: ${formatValue(minPoint.max)}`)
        }
        return lines.join('<br/>')
      },
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: colors.value.textDim },
      axisLine: { lineStyle: { color: colors.value.borderMuted } },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: colors.value.textDim },
      splitLine: { lineStyle: { color: colors.value.borderMuted } },
    },
    series: [
      {
        name: 'band-min',
        type: 'line',
        data: minSeries,
        stack: 'band',
        lineStyle: { opacity: 0 },
        symbol: 'none',
        silent: true,
      },
      {
        name: 'band-range',
        type: 'line',
        data: bandSeries,
        stack: 'band',
        lineStyle: { opacity: 0 },
        areaStyle: {
          color: colors.value.band,
          opacity: 0.18,
        },
        symbol: 'none',
        silent: true,
      },
      {
        name: 'avg',
        type: 'line',
        data: avgSeries,
        symbol: 'circle',
        showSymbol: false,
        lineStyle: { color: colors.value.avg, width: 2 },
      },
      ...(showMedian ? [{
        name: 'median',
        type: 'line',
        data: medianSeries,
        symbol: 'none',
        lineStyle: { color: colors.value.median, width: 1.5, type: 'dashed' },
      }] : []),
    ],
  }
})
</script>
