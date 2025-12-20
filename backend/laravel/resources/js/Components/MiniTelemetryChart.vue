<template>
  <Card 
    class="h-full overflow-hidden surface-card-hover hover:border-[color:var(--border-strong)] transition-all duration-200 group cursor-pointer"
    @click="handleClick"
  >
    <div class="flex items-center justify-between mb-2">
      <div class="text-xs font-medium uppercase tracking-wide text-[color:var(--text-muted)] group-hover:text-[color:var(--text-primary)] transition-colors">
        {{ label }}
      </div>
      <div class="flex items-center gap-2">
        <!-- Индикатор аномалий -->
        <div 
          v-if="hasAnomalies && !loading"
          class="w-2 h-2 rounded-full bg-[color:var(--accent-red)] animate-pulse"
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
      <span v-if="unit" class="text-sm text-[color:var(--text-muted)] ml-1">{{ unit }}</span>
    </div>
    <!-- Sparkline график -->
    <div v-if="loading" class="h-16 flex items-center justify-center">
      <div class="text-xs text-[color:var(--text-dim)]">Загрузка...</div>
    </div>
    <div v-else-if="data.length === 0" class="h-16 flex items-center justify-center">
      <div class="text-xs text-[color:var(--text-dim)]">Нет данных</div>
    </div>
    <div v-else class="h-16 relative">
      <ChartBase :option="chartOption" full-height />
      <!-- Подсказка о клике -->
      <div class="absolute bottom-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <div class="text-[10px] text-[color:var(--text-dim)] bg-[color:var(--bg-surface-strong)] px-1.5 py-0.5 rounded">
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
import { useTheme } from '@/composables/useTheme'

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
  color: 'var(--accent-cyan)'
})

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
    surface: resolveCssColor('--bg-surface-strong', 'rgba(17, 24, 39, 0.95)'),
    border: resolveCssColor('--border-muted', '#374151'),
    text: resolveCssColor('--text-primary', '#f3f4f6'),
  }
})

const resolveColorFromProp = (value?: string): string => {
  if (!value) {
    return resolveCssColor('--accent-cyan', '#3b82f6')
  }
  if (value.startsWith('var(')) {
    const variable = value.slice(4, -1).trim()
    return resolveCssColor(variable, '#3b82f6')
  }
  if (value.startsWith('--')) {
    return resolveCssColor(value, '#3b82f6')
  }
  return value
}

const toRgba = (color: string, alpha: number): string => {
  if (color.startsWith('#')) {
    const hex = color.replace('#', '')
    const normalized = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex
    const int = parseInt(normalized, 16)
    const r = (int >> 16) & 255
    const g = (int >> 8) & 255
    const b = int & 255
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const rgbMatch = color.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/u)
  if (rgbMatch) {
    const [, r, g, b] = rgbMatch
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const rgbaMatch = color.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*[\d.]+\)$/u)
  if (rgbaMatch) {
    const [, r, g, b] = rgbaMatch
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  return color
}

const resolvedColor = computed(() => {
  theme.value
  return resolveColorFromProp(props.color)
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
      backgroundColor: chartPalette.value.surface,
      borderColor: chartPalette.value.border,
      borderWidth: 1,
      textStyle: {
        color: chartPalette.value.text,
        fontSize: 12,
      },
      extraCssText: 'z-index: 99999 !important; box-shadow: var(--shadow-card); padding: 6px 10px; border-radius: 6px;',
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
          color: resolvedColor.value
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: toRgba(resolvedColor.value, 0.25) },
              { offset: 1, color: toRgba(resolvedColor.value, 0) }
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
