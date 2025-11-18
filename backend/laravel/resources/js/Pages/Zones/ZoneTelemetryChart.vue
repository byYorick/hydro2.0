<template>
  <Card class="relative">
    <div class="flex items-center justify-between mb-2">
      <div class="text-sm font-semibold">{{ title }}</div>
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
    <ChartBase :option="option" />
  </Card>
</template>

<script setup>
import { computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'

const props = defineProps({
  title: { type: String, required: true },
  seriesName: { type: String, default: 'value' },
  data: { type: Array, default: () => [] }, // [{ts, value}]
  timeRange: { type: String, default: '24H' },
})

const emit = defineEmits(['time-range-change'])

const setRange = (r) => {
  emit('time-range-change', r)
}

const option = computed(() => ({
  tooltip: { 
    trigger: 'axis',
    confine: false, // Не ограничиваем tooltip границами графика
    appendToBody: true, // Добавляем tooltip в body для правильного z-index
    renderMode: 'html', // Используем HTML рендеринг для лучшего контроля
    formatter: (params) => {
      if (!params || params.length === 0) return ''
      
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
      
      // Определяем, является ли это pH метрикой
      const isPH = props.seriesName.toLowerCase().includes('ph') || 
                   props.title.toLowerCase().includes('ph')
      
      // Для pH показываем 2 знака после точки, для остальных - 1
      const valueStr = typeof point.value === 'number' 
        ? point.value.toFixed(isPH ? 2 : 1)
        : point.value
      
      return `${dateStr}, ${timeStr}<br/>${point.seriesName}: ${valueStr}`
    },
    backgroundColor: 'rgba(17, 24, 39, 0.95)', // neutral-900 с прозрачностью
    borderColor: '#374151',
    borderWidth: 1,
    textStyle: {
      color: '#f3f4f6',
      fontSize: 12,
    },
    extraCssText: 'z-index: 99999 !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2); padding: 8px 12px; border-radius: 6px;',
  },
  grid: { 
    left: 50, 
    right: 20, 
    top: 20, 
    bottom: 40,
    containLabel: true, // Автоматически подстраивает размеры под подписи осей
  },
  xAxis: {
    type: 'time',
    axisLabel: { 
      color: '#9ca3af',
      rotate: 0, // Не поворачиваем подписи
      formatter: (value) => {
        // Форматируем время для компактности
        const date = new Date(value)
        return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      }
    },
    axisLine: { lineStyle: { color: '#374151' } },
    boundaryGap: false, // График начинается от края
  },
  yAxis: {
    type: 'value',
    axisLabel: { 
      color: '#9ca3af',
      formatter: (value) => {
        // Компактный формат для больших чисел
        if (Math.abs(value) >= 1000) {
          return (value / 1000).toFixed(1) + 'k'
        }
        return value.toFixed(1)
      }
    },
    splitLine: { lineStyle: { color: '#1f2937' } },
    scale: false, // Не масштабируем ось автоматически
  },
  series: [
    {
      name: props.seriesName,
      type: 'line',
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2 },
      data: props.data.map(p => [p.ts, p.value]),
      // Ограничиваем область данных
      clip: true, // Обрезаем линию по границам grid
    },
  ],
}))
</script>

