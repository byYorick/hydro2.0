<template>
  <svg
    :width="width"
    :height="height"
    class="sparkline"
    :class="containerClass"
  >
    <!-- Фоновая область (если нужно) -->
    <path
      v-if="showArea && pathData"
      :d="areaPath"
      :fill="areaColor"
      :fill-opacity="areaOpacity"
    />
    
    <!-- Линия графика -->
    <path
      v-if="pathData"
      :d="pathData"
      :stroke="lineColor"
      :stroke-width="strokeWidth"
      fill="none"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    
    <!-- Точки данных (опционально) -->
    <circle
      v-for="(point, index) in points"
      :key="index"
      :cx="point.x"
      :cy="point.y"
      :r="showPoints ? pointRadius : 0"
      :fill="pointColor"
      :class="{ 'opacity-0': !showPoints }"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
  showArea?: boolean
  showPoints?: boolean
  strokeWidth?: number
  pointRadius?: number
  areaOpacity?: number
  containerClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  width: 100,
  height: 30,
  color: 'var(--accent-cyan)',
  showArea: false,
  showPoints: false,
  strokeWidth: 2,
  pointRadius: 2,
  areaOpacity: 0.2,
  containerClass: '',
})

const lineColor = computed(() => props.color)
const pointColor = computed(() => props.color)
const areaColor = computed(() => props.color)

const pathData = computed(() => {
  if (!props.data || props.data.length === 0) return null
  
  const { width, height } = props
  const padding = props.strokeWidth
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2
  
  // Находим min и max значения
  const values = props.data.filter(v => v !== null && v !== undefined && !isNaN(v))
  if (values.length === 0) return null
  
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1 // Избегаем деления на ноль
  
  // Создаем точки
  const points = props.data.map((value, index) => {
    if (value === null || value === undefined || isNaN(value)) {
      return null
    }
    
    const x = padding + (index / (props.data.length - 1 || 1)) * chartWidth
    const y = padding + chartHeight - ((value - min) / range) * chartHeight
    
    return { x, y, value }
  }).filter(p => p !== null) as Array<{ x: number; y: number; value: number }>
  
  if (points.length === 0) return null
  
  // Создаем SVG path
  let path = `M ${points[0].x} ${points[0].y}`
  for (let i = 1; i < points.length; i++) {
    path += ` L ${points[i].x} ${points[i].y}`
  }
  
  return path
})

const areaPath = computed(() => {
  if (!pathData.value || !props.showArea) return null
  
  const { width, height } = props
  const padding = props.strokeWidth
  
  // Добавляем нижнюю линию для закрытия области
  return `${pathData.value} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`
})

const points = computed(() => {
  if (!props.data || props.data.length === 0) return []
  
  const { width, height } = props
  const padding = props.strokeWidth
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2
  
  const values = props.data.filter(v => v !== null && v !== undefined && !isNaN(v))
  if (values.length === 0) return []
  
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  
  return props.data
    .map((value, index) => {
      if (value === null || value === undefined || isNaN(value)) {
        return null
      }
      
      const x = padding + (index / (props.data.length - 1 || 1)) * chartWidth
      const y = padding + chartHeight - ((value - min) / range) * chartHeight
      
      return { x, y, value }
    })
    .filter(p => p !== null) as Array<{ x: number; y: number; value: number }>
})
</script>

<style scoped>
.sparkline {
  display: block;
  max-width: 100%;
  height: auto;
}
</style>

