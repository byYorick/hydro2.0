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
        <div class="flex items-center gap-2">
          <Button 
            size="sm" 
            variant="outline" 
            class="text-xs"
            title="Экспорт данных"
            @click="exportData"
          >
            📥 Экспорт
          </Button>
          <div class="flex gap-1">
            <Button 
              size="sm" 
              :variant="timeRange === '1H' ? 'default' : 'secondary'" 
              @click="setRange('1H')"
            >
              1H
            </Button>
            <Button 
              size="sm" 
              :variant="timeRange === '24H' ? 'default' : 'secondary'" 
              @click="setRange('24H')"
            >
              24H
            </Button>
            <Button 
              size="sm" 
              :variant="timeRange === '7D' ? 'default' : 'secondary'" 
              @click="setRange('7D')"
            >
              7D
            </Button>
            <Button 
              size="sm" 
              :variant="timeRange === '30D' ? 'default' : 'secondary'" 
              @click="setRange('30D')"
            >
              30D
            </Button>
            <Button 
              size="sm" 
              :variant="timeRange === 'ALL' ? 'default' : 'secondary'" 
              @click="setRange('ALL')"
            >
              ALL
            </Button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Легенда -->
    <div class="flex items-center gap-4 mb-2 text-xs">
      <div
        v-for="series in seriesConfig"
        :key="series.name"
        class="flex items-center gap-2"
      >
        <div
          class="w-3 h-0.5 rounded"
          :style="{ backgroundColor: series.color }"
        ></div>
        <span class="text-[color:var(--text-muted)]">{{ series.label }}</span>
        <span
          v-if="series.currentValue !== null && series.currentValue !== undefined"
          class="font-medium"
          :style="{ color: series.color }"
        >
          {{ formatValue(series.currentValue, series.name) }}
        </span>
      </div>
    </div>
    
    <ChartBase :option="option" />
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import type { TelemetrySample } from '@/types'
import { useTheme } from '@/composables/useTheme'

type TimeRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

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
  timeRange?: TimeRange
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Телеметрия',
  series: () => [],
  timeRange: '24H'
})

const emit = defineEmits<{
  'time-range-change': [range: TimeRange]
}>()

const { theme } = useTheme()

const setRange = (r: TimeRange): void => {
  emit('time-range-change', r)
}

const seriesConfig = computed(() => props.series)

// Экспорт данных в CSV
function exportData(): void {
  if (!props.series || props.series.length === 0) {
    alert('Нет данных для экспорта')
    return
  }
  
  // Собираем все уникальные временные метки
  const allTimestamps = new Set<number>()
  props.series.forEach(series => {
    series.data.forEach(item => allTimestamps.add(item.ts))
  })
  const sortedTimestamps = Array.from(allTimestamps).sort((a, b) => a - b)
  
  // Формируем CSV
  const headers = ['Время', ...props.series.map(s => s.label)]
  const rows = sortedTimestamps.map(ts => {
    const date = new Date(ts)
    const timeStr = date.toISOString()
    const values = props.series.map(series => {
      const item = series.data.find(d => d.ts === ts)
      return item ? item.value.toString() : ''
    })
    return [timeStr, ...values]
  })
  
  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.join(','))
  ].join('\n')
  
  // Создаем blob и скачиваем
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `${props.title?.toLowerCase().replace(/\s+/g, '_') || 'telemetry'}_${props.timeRange}_${new Date().toISOString().split('T')[0]}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// Утилита для безопасного извлечения значения из ECharts point
const extractValueFromPoint = (value: unknown): number => {
  if (Array.isArray(value)) {
    const lastElement = value[value.length - 1]
    return typeof lastElement === 'number' ? lastElement : parseFloat(String(lastElement)) || 0
  }
  if (typeof value === 'number') {
    return value
  }
  const parsed = parseFloat(String(value))
  return isNaN(parsed) ? 0 : parsed
}

// Утилита для форматирования значения
// Утилита для форматирования значения оси Y
const formatAxisValue = (value: number): string => {
  if (Math.abs(value) >= 1000) {
    return (value / 1000).toFixed(1) + 'k'
  }
  return value.toFixed(1)
}

// Утилита для форматирования значения в легенде
const formatValue = (value: number | null | undefined, seriesName: string): string => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) {
    return '—'
  }
  const isPH = seriesName.toLowerCase().includes('ph')
  return value.toFixed(isPH ? 2 : 1)
}

// Утилита для форматирования значения в tooltip
const formatTooltipValue = (value: unknown, seriesName: string): string => {
  let actualValue = extractValueFromPoint(value)
  
  // Гарантируем, что actualValue - это валидное число
  if (typeof actualValue !== 'number' || isNaN(actualValue) || !isFinite(actualValue)) {
    actualValue = 0
  }
  
  // Проверяем, не является ли значение timestamp (слишком большое число)
  if (actualValue > 946684800000) {
    actualValue = 0
  }
  
  const numValue = Number(actualValue)
  const isPH = seriesName.toLowerCase().includes('ph')
  return (isNaN(numValue) || !isFinite(numValue) ? 0 : numValue).toFixed(isPH ? 2 : 1)
}

// Утилита для форматирования timestamp в человекочитаемый формат
const formatTimestamp = (timestamp: number | string | null): string => {
  if (timestamp === null) return ''
  
  let ts: number
  if (typeof timestamp === 'string') {
    const parsed = new Date(timestamp).getTime()
    ts = isNaN(parsed) ? 0 : parsed
  } else {
    ts = timestamp
  }
  
  if (ts === 0 || isNaN(ts) || ts <= 946684800000) {
    return String(timestamp)
  }
  
  const date = new Date(ts)
  if (isNaN(date.getTime())) {
    return String(timestamp)
  }
  
  const dateStr = date.toLocaleDateString('ru-RU', { 
    day: '2-digit', 
    month: '2-digit', 
    year: 'numeric' 
  })
  const timeStr = date.toLocaleTimeString('ru-RU', { 
    hour: '2-digit', 
    minute: '2-digit',
    second: '2-digit'
  })
  return `${dateStr}, ${timeStr}`
}

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
    tooltipBg: resolveCssColor('--bg-surface-strong', 'rgba(17, 24, 39, 0.95)'),
    borderMuted: resolveCssColor('--border-muted', '#374151'),
    borderStrong: resolveCssColor('--border-strong', '#4b5563'),
    textPrimary: resolveCssColor('--text-primary', '#f3f4f6'),
    textDim: resolveCssColor('--text-dim', '#9ca3af'),
    badgeNeutralBg: resolveCssColor('--badge-neutral-bg', 'rgba(75, 85, 99, 0.2)'),
    badgeInfoBg: resolveCssColor('--badge-info-bg', 'rgba(96, 165, 250, 0.2)'),
    accentCyan: resolveCssColor('--accent-cyan', '#60a5fa'),
  }
})

const option = computed(() => {
  const allDataLength = Math.max(...props.series.map(s => s.data?.length || 0))
  const hasLargeDataset = allDataLength > 50
  
  // Определяем, нужны ли две оси Y (если разные единицы измерения)
  const hasDifferentUnits = props.series.length > 1 && 
    props.series.some(s => s.yAxisIndex !== undefined && s.yAxisIndex !== 0)
  
  const palette = chartPalette.value

  return {
    tooltip: { 
      trigger: 'axis',
      confine: false,
      appendToBody: true,
      renderMode: 'html',
      formatter: (params: unknown) => {
        if (!params || !Array.isArray(params) || params.length === 0) return ''
        
        const points = params as Array<{ axisValue: number | string; value: number; seriesName: string; color: string; data?: { ts: number } }>
        const point = points[0]
        
        // Получаем timestamp из исходных данных или axisValue
        const timestamp = (point.data && typeof point.data.ts === 'number') 
          ? point.data.ts 
          : point.axisValue
        
        const dateTimeStr = formatTimestamp(timestamp)
        
        const lines = points.map(p => {
          const valueStr = formatTooltipValue(p.value, p.seriesName)
          return `<div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 10px; height: 2px; background-color: ${p.color};"></span>
            <span>${p.seriesName}: <strong>${valueStr}</strong></span>
          </div>`
        }).join('')
        
        return `${dateTimeStr}<br/>${lines}`
      },
      backgroundColor: palette.tooltipBg,
      borderColor: palette.borderMuted,
      borderWidth: 1,
      textStyle: {
        color: palette.textPrimary,
        fontSize: 12,
      },
      extraCssText: 'z-index: 99999 !important; box-shadow: var(--shadow-card); padding: 8px 12px; border-radius: 6px;',
    },
    legend: {
      show: false, // Используем кастомную легенду
    },
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
        rotate: 0,
        formatter: (value: number) => {
          const date = new Date(value)
          return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        }
      },
      axisLine: { lineStyle: { color: palette.borderMuted } },
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: props.series[0]?.label || '',
        nameTextStyle: { color: palette.textDim },
        position: 'left',
        axisLabel: { 
          color: props.series[0]?.color || palette.textDim,
          formatter: formatAxisValue,
        },
        splitLine: { lineStyle: { color: palette.borderMuted } },
        scale: false,
      },
      ...(hasDifferentUnits ? [{
        type: 'value',
        name: props.series.find(s => s.yAxisIndex === 1)?.label || '',
        nameTextStyle: { color: palette.textDim },
        position: 'right',
        axisLabel: { 
          color: props.series.find(s => s.yAxisIndex === 1)?.color || palette.textDim,
          formatter: formatAxisValue,
        },
        splitLine: { show: false },
        scale: false,
      }] : []),
    ],
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
        minValueSpan: allDataLength > 0 && props.series[0]?.data?.length > 0
          ? Math.min(3600000, (props.series[0].data[props.series[0].data.length - 1]?.ts || 0) - (props.series[0].data[0]?.ts || 0) || 3600000)
          : 3600000,
        maxValueSpan: allDataLength > 0 && props.series[0]?.data?.length > 0
          ? (props.series[0].data[props.series[0].data.length - 1]?.ts || 0) - (props.series[0].data[0]?.ts || 0) || 86400000
          : 86400000,
        filterMode: 'none',
      },
      ...(hasLargeDataset ? [{
        type: 'slider',
        start: 0,
        end: 100,
        height: 24,
        bottom: 10,
        handleIcon: 'path://M30.9,53.2C16.8,53.2,5.3,41.7,5.3,27.6S16.8,2,30.9,2C45,2,56.4,13.5,56.4,27.6S45,53.2,30.9,53.2z M30.9,3.5C17.6,3.5,6.8,14.4,6.8,27.6c0,13.3,10.8,24.1,24.1,24.1C44.2,51.7,55,40.9,55,27.6C54.9,14.4,44.1,3.5,30.9,3.5z M36.9,35.8c0,0.6-0.4,1-1,1H26.5c-0.6,0-1-0.4-1-1V19.4c0-0.6,0.4-1,1-1h9.4c0.6,0,1,0.4,1,1V35.8z',
        handleSize: '80%',
        handleStyle: {
          color: palette.borderStrong,
          borderColor: palette.borderMuted,
        },
        textStyle: {
          color: palette.textDim,
          fontSize: 10,
        },
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
        minValueSpan: allDataLength > 0 && props.series[0]?.data?.length > 0
          ? Math.min(3600000, (props.series[0].data[props.series[0].data.length - 1]?.ts || 0) - (props.series[0].data[0]?.ts || 0) || 3600000)
          : 3600000,
      }] : []),
    ],
    series: props.series.map((series, index) => {
      const seriesConfig: any = {
        name: series.label,
        type: 'line',
        showSymbol: false,
        smooth: true,
        lineStyle: { 
          width: 2,
          color: series.color,
        },
        itemStyle: {
          color: series.color,
        },
        data: series.data.map(p => [p.ts, p.value]),
        clip: true,
        large: hasLargeDataset,
        largeThreshold: 100,
        yAxisIndex: series.yAxisIndex || 0,
        z: props.series.length - index, // Порядок отрисовки
      }

      // Добавляем визуализацию целевого диапазона (markArea)
      if (series.targetRange && series.targetRange.min !== undefined && series.targetRange.max !== undefined) {
        const targetColor = resolveCssColor('--badge-success-bg', 'rgba(34, 197, 94, 0.15)')
        seriesConfig.markArea = {
          silent: true,
          itemStyle: {
            color: targetColor,
            borderColor: resolveCssColor('--accent-green', '#22c55e'),
            borderWidth: 1,
            borderType: 'dashed',
          },
          data: [
            [
              { yAxis: series.targetRange.min },
              { yAxis: series.targetRange.max },
            ],
          ],
          label: {
            show: false,
          },
        }
      }

      return seriesConfig
    }),
  }
}) as any
</script>
