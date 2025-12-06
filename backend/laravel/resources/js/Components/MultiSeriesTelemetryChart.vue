<template>
  <Card class="relative">
    <div class="flex items-center justify-between mb-2">
      <div class="text-sm font-semibold">{{ title }}</div>
      <div class="flex items-center gap-2">
        <div class="text-xs text-neutral-500 hidden sm:inline">
          <span class="mr-2">🖱️ Колесо мыши — zoom</span>
          <span>Перетаскивание — pan</span>
        </div>
        <div class="flex items-center gap-2">
          <Button 
            size="sm" 
            variant="outline" 
            @click="exportData"
            class="text-xs"
            title="Экспорт данных"
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
        <span class="text-neutral-400">{{ series.label }}</span>
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

type TimeRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

interface SeriesConfig {
  name: string
  label: string
  color: string
  data: TelemetrySample[]
  currentValue?: number | null
  yAxisIndex?: number
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

const formatValue = (value: number | null | undefined, seriesName: string): string => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) {
    return '—'
  }
  const isPH = seriesName.toLowerCase().includes('ph')
  return value.toFixed(isPH ? 2 : 1)
}

const option = computed(() => {
  const allDataLength = Math.max(...props.series.map(s => s.data?.length || 0))
  const hasLargeDataset = allDataLength > 50
  
  // Определяем, нужны ли две оси Y (если разные единицы измерения)
  const hasDifferentUnits = props.series.length > 1 && 
    props.series.some(s => s.yAxisIndex !== undefined && s.yAxisIndex !== 0)
  
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
        
        // Для оси типа 'time' ECharts может передавать axisValue в разных форматах
        // Также можем использовать data.ts из исходных данных, если доступно
        let timestamp: number | null = null
        
        // Сначала пытаемся получить timestamp из исходных данных точки
        if (point.data && typeof point.data.ts === 'number') {
          timestamp = point.data.ts
        } else {
          // Иначе используем axisValue
          const axisValue = point.axisValue
          if (typeof axisValue === 'string') {
            const parsed = new Date(axisValue).getTime()
            if (!isNaN(parsed)) {
              timestamp = parsed
            }
          } else if (typeof axisValue === 'number') {
            timestamp = axisValue
          }
        }
        
        let dateTimeStr = ''
        
        if (timestamp !== null && !isNaN(timestamp) && timestamp > 946684800000) {
          const date = new Date(timestamp)
          if (!isNaN(date.getTime())) {
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
            dateTimeStr = `${dateStr}, ${timeStr}`
          } else {
            dateTimeStr = String(timestamp)
          }
        } else {
          // Если не удалось получить timestamp, используем axisValue как есть
          dateTimeStr = String(point.axisValue)
        }
        
        const lines = points.map(p => {
          const isPH = p.seriesName.toLowerCase().includes('ph')
          
          // ECharts может передавать value как массив [timestamp, value] или просто value
          let actualValue: number
          if (Array.isArray(p.value)) {
            // Если value - массив, берем последний элемент (значение)
            const lastElement = p.value[p.value.length - 1]
            actualValue = typeof lastElement === 'number' ? lastElement : parseFloat(String(lastElement)) || 0
          } else if (typeof p.value === 'number') {
            actualValue = p.value
          } else {
            // Если это не число и не массив, пытаемся преобразовать
            const parsed = parseFloat(String(p.value))
            actualValue = isNaN(parsed) ? 0 : parsed
          }
          
          // Гарантируем, что actualValue - это валидное число
          if (typeof actualValue !== 'number' || isNaN(actualValue) || !isFinite(actualValue)) {
            actualValue = 0
          }
          
          // Проверяем, не является ли значение timestamp (слишком большое число)
          // Если значение больше 946684800000 (2000-01-01), это скорее всего timestamp, а не значение
          if (actualValue > 946684800000) {
            // Это timestamp, не отображаем его как значение
            actualValue = 0
          }
          
          // Финальная проверка перед вызовом toFixed
          const numValue = Number(actualValue)
          const valueStr = (isNaN(numValue) || !isFinite(numValue) ? 0 : numValue).toFixed(isPH ? 2 : 1)
          
          return `<div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 10px; height: 2px; background-color: ${p.color};"></span>
            <span>${p.seriesName}: <strong>${valueStr}</strong></span>
          </div>`
        }).join('')
        
        return `${dateTimeStr}<br/>${lines}`
      },
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: '#374151',
      borderWidth: 1,
      textStyle: {
        color: '#f3f4f6',
        fontSize: 12,
      },
      extraCssText: 'z-index: 99999 !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2); padding: 8px 12px; border-radius: 6px;',
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
        color: '#9ca3af',
        rotate: 0,
        formatter: (value: number) => {
          const date = new Date(value)
          return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        }
      },
      axisLine: { lineStyle: { color: '#374151' } },
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: props.series[0]?.label || '',
        nameTextStyle: { color: '#9ca3af' },
        position: 'left',
        axisLabel: { 
          color: props.series[0]?.color || '#9ca3af',
          formatter: (value: number) => {
            if (Math.abs(value) >= 1000) {
              return (value / 1000).toFixed(1) + 'k'
            }
            return value.toFixed(1)
          }
        },
        splitLine: { lineStyle: { color: '#1f2937' } },
        scale: false,
      },
      ...(hasDifferentUnits ? [{
        type: 'value',
        name: props.series.find(s => s.yAxisIndex === 1)?.label || '',
        nameTextStyle: { color: '#9ca3af' },
        position: 'right',
        axisLabel: { 
          color: props.series.find(s => s.yAxisIndex === 1)?.color || '#9ca3af',
          formatter: (value: number) => {
            if (Math.abs(value) >= 1000) {
              return (value / 1000).toFixed(1) + 'k'
            }
            return value.toFixed(1)
          }
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
          color: '#4b5563',
          borderColor: '#6b7280',
        },
        textStyle: {
          color: '#9ca3af',
          fontSize: 10,
        },
        borderColor: '#374151',
        fillerColor: 'rgba(75, 85, 99, 0.2)',
        dataBackground: {
          lineStyle: { color: '#4b5563' },
          areaStyle: { color: 'rgba(75, 85, 99, 0.1)' },
        },
        selectedDataBackground: {
          lineStyle: { color: '#60a5fa' },
          areaStyle: { color: 'rgba(96, 165, 250, 0.2)' },
        },
        minValueSpan: allDataLength > 0 && props.series[0]?.data?.length > 0
          ? Math.min(3600000, (props.series[0].data[props.series[0].data.length - 1]?.ts || 0) - (props.series[0].data[0]?.ts || 0) || 3600000)
          : 3600000,
      }] : []),
    ],
    series: props.series.map((series, index) => ({
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
    })),
  }
})
</script>

