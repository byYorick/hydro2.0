import { computed, type Ref } from 'vue'
import type { EChartsOption, LineSeriesOption, SeriesOption } from 'echarts'
import type { TelemetryRange, TelemetrySample } from '@/types'
import type { ChartPalette } from '@/composables/useChartColors'

interface TelemetrySeriesInput {
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

interface BuildTelemetryChartOptionsParams {
  palette: ChartPalette
  series: TelemetrySeriesInput[]
  timeRange: TelemetryRange
}

const PRESET = {
  lineWidth: 2,
  areaOpacity: 0.08,
  animation: false,
} as const

const formatAxisTimestamp = (timestamp: number, timeRange: TelemetryRange): string => {
  const date = new Date(timestamp)
  if (timeRange === '1H') {
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
  if (timeRange === '24H') {
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  if (timeRange === '7D' || timeRange === '30D') {
    return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

const formatTooltipTimestamp = (timestamp: number): string => {
  return new Date(timestamp).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const formatValue = (value: number, seriesName: string): string => {
  const isPh = seriesName.toLowerCase().includes('ph')
  return value.toFixed(isPh ? 2 : 1)
}

const axisFormatterByLabel = (label: string): ((value: number) => string) => {
  const normalized = label.trim().toLowerCase()
  if (normalized.includes('ph')) {
    return (value: number) => value.toFixed(2)
  }
  return (value: number) => value.toFixed(1)
}

const defaultZoomStartByRange: Record<TelemetryRange, number> = {
  '1H': 0,
  '24H': 50,
  '7D': 70,
  '30D': 85,
  'ALL': 95,
}

const resolveAxisBounds = (seriesLabel: string): { min?: number; max?: number } => {
  const normalized = seriesLabel.trim().toLowerCase()
  if (normalized.includes('ph')) {
    return { min: 3, max: 10 }
  }
  if (normalized.includes('ec')) {
    return { min: 0, max: 5 }
  }
  if (normalized.includes('soil') || normalized.includes('влажность')) {
    return { min: 0, max: 100 }
  }

  return {}
}

const toLineSeries = (
  series: TelemetrySeriesInput,
  palette: ChartPalette,
  showCurrentValueLabel: boolean,
): LineSeriesOption => {
  const output: LineSeriesOption = {
    name: series.label,
    type: 'line',
    showSymbol: false,
    smooth: true,
    lineStyle: {
      width: PRESET.lineWidth,
      color: series.color,
    },
    itemStyle: {
      color: series.color,
    },
    areaStyle: {
      opacity: PRESET.areaOpacity,
      color: series.color,
    },
    data: series.data.map((point) => [point.ts, point.value]),
    clip: true,
    yAxisIndex: series.yAxisIndex ?? 0,
  }

  if (typeof series.currentValue === 'number' && Number.isFinite(series.currentValue)) {
    output.markLine = {
      symbol: 'none',
      silent: true,
      lineStyle: {
        color: series.color,
        type: 'dashed',
        width: 1,
      },
      label: {
        show: showCurrentValueLabel,
        formatter: `Текущее: ${formatValue(series.currentValue, series.label)}`,
        color: palette.textDim,
        fontSize: 11,
      },
      data: [{ yAxis: series.currentValue }],
    }
  }

  if (series.targetRange?.min !== undefined && series.targetRange?.max !== undefined) {
    output.markArea = {
      silent: true,
      itemStyle: {
        color: palette.badgeSuccessBg,
        borderColor: palette.accentGreen,
        borderWidth: 1,
        borderType: 'dashed',
      },
      data: [[{ yAxis: series.targetRange.min }, { yAxis: series.targetRange.max }]],
      label: { show: false },
    }
  }

  return output
}

export function buildTelemetryChartOptions(params: BuildTelemetryChartOptionsParams): EChartsOption {
  const { palette, series, timeRange } = params
  const allDataLength = Math.max(...series.map((item) => item.data.length), 0)
  const hasLargeDataset = allDataLength > 50
  const hasDifferentUnits = series.some((item) => (item.yAxisIndex ?? 0) !== 0)
  const firstSeries = series[0]
  const firstSeriesSpan = firstSeries && firstSeries.data.length > 1
    ? firstSeries.data[firstSeries.data.length - 1].ts - firstSeries.data[0].ts
    : 0
  const minValueSpan = Math.min(3_600_000, firstSeriesSpan || 3_600_000)
  const maxValueSpan = firstSeriesSpan || 86_400_000
  const defaultZoomStart = allDataLength > 0 ? defaultZoomStartByRange[timeRange] : 0

  const showCurrentValueLabel = series.length === 1
  const chartSeries: SeriesOption[] = series.map((item) =>
    toLineSeries(item, palette, showCurrentValueLabel),
  )
  const primarySeries = firstSeries
  const secondarySeries = series.find((item) => item.yAxisIndex === 1)
  const primaryAxisBounds = resolveAxisBounds(primarySeries?.label ?? '')
  const secondaryAxisBounds = resolveAxisBounds(secondarySeries?.label ?? '')

  return {
    tooltip: {
      trigger: 'axis',
      confine: false,
      appendToBody: true,
      renderMode: 'html',
      formatter: (rawParams: unknown) => {
        if (!Array.isArray(rawParams) || rawParams.length === 0) {
          return ''
        }

        const paramsList = (rawParams as Array<{ axisValue: number; value: [number, number] | number; seriesName: string; color: string }>)
          .sort((left, right) => {
            const leftValue = Array.isArray(left.value) ? Number(left.value[1]) : Number(left.value)
            const rightValue = Array.isArray(right.value) ? Number(right.value[1]) : Number(right.value)
            return rightValue - leftValue
          })
        const timestamp = Number(paramsList[0].axisValue)
        const lines = paramsList.map((item) => {
          const numeric = Array.isArray(item.value) ? Number(item.value[1]) : Number(item.value)
          return `<div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 10px; height: 2px; background-color: ${item.color};"></span>
            <span>${item.seriesName}: <strong>${formatValue(numeric, item.seriesName)}</strong></span>
          </div>`
        }).join('')

        return `${formatTooltipTimestamp(timestamp)}<br/>${lines}`
      },
      backgroundColor: palette.tooltipBg,
      borderColor: palette.borderMuted,
      borderWidth: 1,
      textStyle: { color: palette.textPrimary, fontSize: 12 },
      extraCssText: 'z-index: 99999 !important; box-shadow: var(--shadow-card); padding: 8px 12px; border-radius: 6px;',
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: palette.tooltipBg },
    },
    legend: { show: false },
    grid: {
      left: 50,
      right: hasDifferentUnits ? 50 : 20,
      top: 20,
      bottom: hasLargeDataset ? 80 : 40,
      containLabel: true,
    },
    xAxis: {
      type: 'time',
      axisLabel: {
        color: palette.textDim,
        formatter: (value: number) => formatAxisTimestamp(value, timeRange),
      },
      axisLine: { lineStyle: { color: palette.borderMuted } },
      boundaryGap: [0, 0],
    },
    yAxis: [
      {
        type: 'value',
        name: firstSeries?.label ?? '',
        nameTextStyle: { color: palette.textDim },
        position: 'left',
        axisLabel: {
          color: firstSeries?.color ?? palette.textDim,
          formatter: axisFormatterByLabel(firstSeries?.label ?? ''),
        },
        splitLine: { lineStyle: { color: palette.borderMuted } },
        scale: false,
        min: primaryAxisBounds.min,
        max: primaryAxisBounds.max,
      },
      ...(hasDifferentUnits
        ? [{
            type: 'value' as const,
            name: series.find((item) => item.yAxisIndex === 1)?.label ?? '',
            nameTextStyle: { color: palette.textDim },
            position: 'right' as const,
            axisLabel: {
              color: series.find((item) => item.yAxisIndex === 1)?.color ?? palette.textDim,
              formatter: axisFormatterByLabel(series.find((item) => item.yAxisIndex === 1)?.label ?? ''),
            },
            splitLine: { show: false },
            scale: false,
            min: secondaryAxisBounds.min,
            max: secondaryAxisBounds.max,
          }]
        : []),
    ],
    dataZoom: [
      {
        type: 'inside',
        start: defaultZoomStart,
        end: 100,
        minValueSpan,
        maxValueSpan,
        filterMode: 'none',
      },
      ...(hasLargeDataset
        ? [{
            type: 'slider',
            start: defaultZoomStart,
            end: 100,
            height: 24,
            bottom: 10,
            handleSize: '80%',
            textStyle: { color: palette.textDim, fontSize: 10 },
            borderColor: palette.borderMuted,
            fillerColor: palette.badgeNeutralBg,
            dataBackground: {
              lineStyle: { color: palette.borderStrong },
              areaStyle: { color: palette.badgeNeutralBg },
            },
            selectedDataBackground: {
              lineStyle: { color: palette.accentCyan },
              areaStyle: { color: palette.badgeInfoBg },
            },
            minValueSpan,
          }]
        : []),
    ],
    series: chartSeries,
    animation: PRESET.animation,
  }
}

export function useTelemetryChartOptions(
  palette: Ref<ChartPalette>,
  series: Ref<TelemetrySeriesInput[]>,
  timeRange: Ref<TelemetryRange>,
) {
  const option = computed<EChartsOption>(() => {
    return buildTelemetryChartOptions({
      palette: palette.value,
      series: series.value,
      timeRange: timeRange.value,
    })
  })

  return { option }
}
