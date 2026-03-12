<template>
  <Card 
    class="h-full overflow-hidden hover:border-neutral-700 transition-all duration-200 hover:shadow-lg group cursor-pointer"
    @click="handleClick"
  >
    <div class="flex items-center justify-between mb-2">
      <div class="text-xs font-medium uppercase tracking-wide text-neutral-400 group-hover:text-neutral-300 transition-colors">
        {{ label }}
      </div>
      <div class="flex items-center gap-2">
        <!-- Индикатор аномалий -->
        <div 
          v-if="hasAnomalies && !loading"
          class="w-2 h-2 rounded-full bg-red-400 animate-pulse"
          title="Обнаружены аномалии"
        ></div>
        <!-- Индикатор активности -->
        <div 
          v-if="currentValue !== null && !loading"
          class="w-2 h-2 rounded-full animate-pulse"
          :style="{ backgroundColor: color }"
        ></div>
      </div>
    </div>
    <div class="text-2xl font-bold mb-2" :style="{ color: color }">
      {{ currentValue !== null ? formatValue(currentValue) : '-' }}
      <span v-if="unit" class="text-sm text-neutral-400 ml-1">{{ unit }}</span>
    </div>
    <!-- Sparkline график -->
    <div v-if="loading" class="h-16 flex items-center justify-center">
      <div class="text-xs text-neutral-500">Загрузка...</div>
    </div>
    <div v-else-if="data.length === 0" class="h-16 flex items-center justify-center">
      <div class="text-xs text-neutral-500">Нет данных</div>
    </div>
    <div v-else class="h-16 relative">
      <ChartBase :option="chartOption" full-height />
      <!-- Подсказка о клике -->
      <div class="absolute bottom-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <div class="text-[10px] text-neutral-500 bg-neutral-900/80 px-1.5 py-0.5 rounded">
          Клик для деталей
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import ChartBase from '@/Components/ChartBase.vue'

interface TelemetryDataPoint {
  ts: number
  value?: number
  min?: number
  max?: number
  avg?: number
}

interface Props {
  label: string
  data?: TelemetryDataPoint[]
  currentValue?: number | null
  unit?: string
  loading?: boolean
  color?: string
  zoneId?: number
  metric?: string
}

const emit = defineEmits<{
  click: []
  'open-detail': [zoneId: number, metric: string]
}>()

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  currentValue: null,
  unit: '',
  loading: false,
  color: '#3b82f6'
})

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    // Для pH показываем 2 знака после точки, для остальных - 1
    const isPH = props.label.toLowerCase().includes('ph')
    return value.toFixed(isPH ? 2 : 1)
  }
  return String(value)
}

// Определение аномалий (простое: значения вне нормального диапазона)
const hasAnomalies = computed(() => {
  if (!props.data || props.data.length === 0) return false
  
  // Простая проверка: если есть значения, сильно отличающиеся от среднего
  const values = props.data
    .map(item => item.avg !== undefined ? item.avg : item.value)
    .filter(v => v !== null && v !== undefined) as number[]
  
  if (values.length < 3) return false
  
  const avg = values.reduce((a, b) => a + b, 0) / values.length
  const variance = values.reduce((sum, v) => sum + Math.pow(v - avg, 2), 0) / values.length
  const stdDev = Math.sqrt(variance)
  
  // Аномалия: значение отличается от среднего более чем на 2 стандартных отклонения
  return values.some(v => Math.abs(v - avg) > 2 * stdDev)
})

const handleClick = () => {
  emit('click')
  if (props.zoneId && props.metric) {
    emit('open-detail', props.zoneId, props.metric)
  }
}

const chartOption = computed(() => {
  if (!props.data || props.data.length === 0) {
    return {
      grid: { left: 8, right: 8, top: 8, bottom: 8 },
      xAxis: { show: false },
      yAxis: { show: false },
    }
  }

  return {
    tooltip: {
      trigger: 'axis',
      confine: false, // Не ограничиваем tooltip границами графика
      appendToBody: true, // Добавляем tooltip в body для правильного z-index
      renderMode: 'html', // Используем HTML рендеринг для лучшего контроля
      formatter: (params) => {
        const point = params[0]
        const date = new Date(point.axisValue)
        // Форматируем время в понятном формате: "25.12.2024, 15:30"
        const dateStr = date.toLocaleDateString('ru-RU', { 
          day: '2-digit', 
          month: '2-digit', 
          year: 'numeric' 
        })
        const timeStr = date.toLocaleTimeString('ru-RU', { 
          hour: '2-digit', 
          minute: '2-digit' 
        })
        
        // Для pH показываем 2 знака после точки
        const isPH = props.label.toLowerCase().includes('ph')
        const valueStr = typeof point.value === 'number' 
          ? point.value.toFixed(isPH ? 2 : 1)
          : point.value
        
        return `${dateStr}, ${timeStr}<br/>${point.seriesName}: ${valueStr}${props.unit ? ' ' + props.unit : ''}`
      },
      backgroundColor: 'rgba(17, 24, 39, 0.95)', // neutral-900 с прозрачностью
      borderColor: '#374151',
      borderWidth: 1,
      textStyle: {
        color: '#f3f4f6',
        fontSize: 12,
      },
      extraCssText: 'z-index: 99999 !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2); padding: 6px 10px; border-radius: 6px;',
    },
    grid: { 
      left: 4, 
      right: 4, 
      top: 4, 
      bottom: 4,
      containLabel: true, // Автоматически подстраивает размеры
    },
    xAxis: {
      type: 'time',
      show: false,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      show: false,
      scale: true,
    },
    series: [
      {
        name: props.label,
        type: 'line',
        showSymbol: false,
        smooth: true,
        lineStyle: { 
          width: 1.5,
          color: props.color
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: props.color + '40' },
              { offset: 1, color: props.color + '00' }
            ]
          }
        },
        data: props.data.map(item => {
          // Используем avg если есть, иначе value
          const value = item.avg !== undefined ? item.avg : item.value
          return [item.ts, value]
        }),
      },
    ],
  }
})
</script>

