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

<script setup lang="ts">
import { computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import type { TelemetrySample } from '@/types'

type TimeRange = '1H' | '24H' | '7D' | '30D' | 'ALL'

interface Props {
  title: string
  seriesName?: string
  data?: TelemetrySample[]
  timeRange?: TimeRange
}

const props = withDefaults(defineProps<Props>(), {
  seriesName: 'value',
  data: () => [],
  timeRange: '24H'
})

const emit = defineEmits<{
  'time-range-change': [range: TimeRange]
}>()

const setRange = (r: TimeRange): void => {
  emit('time-range-change', r)
}

const option = computed(() => {
  const dataLength = props.data?.length || 0
  const hasLargeDataset = dataLength > 100 // Показываем DataZoom для больших наборов данных
  
  return {
    tooltip: { 
      trigger: 'axis',
      confine: false, // Не ограничиваем tooltip границами графика
      appendToBody: true, // Добавляем tooltip в body для правильного z-index
      renderMode: 'html', // Используем HTML рендеринг для лучшего контроля
      formatter: (params: unknown) => {
        if (!params || !Array.isArray(params) || params.length === 0) return ''
        
        const point = params[0] as { axisValue: number; value: number; seriesName: string }
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
          : String(point.value)
        
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
      bottom: hasLargeDataset ? 80 : 40, // Увеличиваем место для DataZoom
      containLabel: true, // Автоматически подстраивает размеры под подписи осей
    },
    xAxis: {
      type: 'time',
      axisLabel: { 
        color: '#9ca3af',
        rotate: 0, // Не поворачиваем подписи
        formatter: (value: number) => {
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
        formatter: (value: number) => {
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
    // DataZoom для навигации по большим наборам данных
    dataZoom: hasLargeDataset ? [
      {
        type: 'inside', // Внутренний DataZoom (скролл мышью)
        start: 0,
        end: 100,
        minValueSpan: 3600000, // Минимум 1 час
      },
      {
        type: 'slider', // Внешний DataZoom (ползунок внизу)
        start: 0,
        end: 100,
        height: 20,
        bottom: 10,
        handleIcon: 'path://M30.9,53.2C16.8,53.2,5.3,41.7,5.3,27.6S16.8,2,30.9,2C45,2,56.4,13.5,56.4,27.6S45,53.2,30.9,53.2z M30.9,3.5C17.6,3.5,6.8,14.4,6.8,27.6c0,13.3,10.8,24.1,24.1,24.1C44.2,51.7,55,40.9,55,27.6C54.9,14.4,44.1,3.5,30.9,3.5z M36.9,35.8c0,0.6-0.4,1-1,1H26.5c-0.6,0-1-0.4-1-1V19.4c0-0.6,0.4-1,1-1h9.4c0.6,0,1,0.4,1,1V35.8z',
        handleSize: '80%',
        handleStyle: {
          color: '#4b5563',
          borderColor: '#6b7280',
        },
        textStyle: {
          color: '#9ca3af',
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
        minValueSpan: 3600000, // Минимум 1 час
      },
    ] : undefined,
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
        // Оптимизация для больших наборов данных
        large: hasLargeDataset,
        largeThreshold: 100,
      },
    ],
  }
})
</script>

