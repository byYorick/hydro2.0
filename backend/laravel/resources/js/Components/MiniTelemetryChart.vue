<template>
  <Card class="h-full overflow-hidden">
    <div class="text-xs text-neutral-400 mb-1">{{ label }}</div>
    <div class="text-lg font-semibold mb-2">
      {{ currentValue !== null ? formatValue(currentValue) : '-' }}
      <span v-if="unit" class="text-sm text-neutral-400">{{ unit }}</span>
    </div>
    <div v-if="loading" class="h-16 flex items-center justify-center">
      <div class="text-xs text-neutral-500">Загрузка...</div>
    </div>
    <div v-else-if="data.length === 0" class="h-16 flex items-center justify-center">
      <div class="text-xs text-neutral-500">Нет данных</div>
    </div>
    <div v-else class="h-16 relative">
      <ChartBase :option="chartOption" full-height />
    </div>
  </Card>
</template>

<script setup>
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import ChartBase from '@/Components/ChartBase.vue'

const props = defineProps({
  label: {
    type: String,
    required: true
  },
  data: {
    type: Array,
    default: () => [] // [{ts, value, min, max, avg}]
  },
  currentValue: {
    type: Number,
    default: null
  },
  unit: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  },
  color: {
    type: String,
    default: '#3b82f6' // синий по умолчанию
  }
})

function formatValue(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    // Для pH показываем 2 знака после точки, для остальных - 1
    const isPH = props.label.toLowerCase().includes('ph')
    return value.toFixed(isPH ? 2 : 1)
  }
  return value
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

