<template>
  <Card
    class="metric-indicator-card surface-card-hover"
    :class="{ 'metric-indicator-large': size === 'large' }"
  >
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1 min-w-0">
        <div class="text-xs font-medium uppercase tracking-wide text-[color:var(--text-dim)] mb-1">
          {{ label }}
        </div>
        <div class="flex items-baseline gap-2">
          <div 
            class="font-bold transition-colors"
            :class="[
              size === 'large' ? 'text-4xl' : size === 'medium' ? 'text-2xl' : 'text-xl',
              valueColorClass
            ]"
          >
            {{ formattedValue }}
          </div>
          <div
            v-if="unit"
            class="text-sm text-[color:var(--text-muted)]"
          >
            {{ unit }}
          </div>
        </div>
      </div>
      
      <!-- Статус индикатор -->
      <StatusIndicator 
        v-if="status"
        :status="status"
        :pulse="isCritical"
        size="small"
      />
    </div>

    <!-- Целевое значение и отклонение -->
    <div
      v-if="target !== null && target !== undefined"
      class="mt-2 space-y-1"
    >
      <div class="flex items-center justify-between text-xs">
        <span class="text-[color:var(--text-dim)]">Цель:</span>
        <span class="font-medium">{{ formatTarget(target) }}</span>
      </div>
      
      <!-- Отклонение от цели -->
      <div
        v-if="deviation !== null"
        class="flex items-center gap-1 text-xs"
      >
        <span 
          :class="deviationClass"
        >
          {{ deviation > 0 ? '+' : '' }}{{ formatDeviation(deviation) }}
        </span>
        <span class="text-[color:var(--text-dim)]">от цели</span>
      </div>
    </div>

    <!-- Тренд (sparkline или стрелка) -->
    <div
      v-if="showTrend && trend !== null"
      class="mt-2 flex items-center gap-1"
    >
      <div 
        v-if="trend !== null"
        class="flex items-center gap-1 text-xs"
        :class="trendColorClass"
      >
        <svg 
          v-if="trend > 0"
          class="w-3 h-3"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
          />
        </svg>
        <svg 
          v-else-if="trend < 0"
          class="w-3 h-3"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"
          />
        </svg>
        <svg 
          v-else
          class="w-3 h-3"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M5 12h14"
          />
        </svg>
        <span>{{ Math.abs(trend).toFixed(1) }}%</span>
      </div>
    </div>

    <!-- Sparkline график тренда -->
    <div
      v-if="sparklineData && sparklineData.length > 0"
      class="mt-3"
    >
      <Sparkline
        :data="sparklineData"
        :width="120"
        :height="30"
        :color="sparklineColor"
        :show-area="true"
        :stroke-width="1.5"
        :area-opacity="0.15"
      />
    </div>

    <!-- Мини-график (gauge) -->
    <div
      v-else-if="showGauge && target !== null"
      class="mt-3"
    >
      <div class="relative h-1 bg-[color:var(--bg-elevated)] rounded-full overflow-hidden">
        <div 
          class="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
          :class="gaugeColorClass"
          :style="{ width: `${gaugePercentage}%` }"
        ></div>
      </div>
    </div>

    <!-- Дополнительный контент (footer slot) -->
    <div
      v-if="$slots.footer"
      class="mt-3 pt-3 border-t border-[color:var(--border-muted)]"
    >
      <slot name="footer"></slot>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from './Card.vue'
import StatusIndicator from './StatusIndicator.vue'
import Sparkline from './Sparkline.vue'

interface Props {
  label: string
  value: number | null
  unit?: string
  target?: number | null
  status?: string | 'success' | 'warning' | 'danger' | 'neutral' | 'info'
  trend?: number | null
  sparklineData?: number[] | null
  size?: 'small' | 'medium' | 'large'
  showTrend?: boolean
  showGauge?: boolean
  formatValue?: (value: number) => string
  criticalThreshold?: number
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  target: null,
  status: '',
  trend: null,
  sparklineData: null,
  size: 'medium',
  showTrend: false,
  showGauge: false,
  criticalThreshold: 0.1,
})

const formattedValue = computed(() => {
  if (props.value === null || props.value === undefined) {
    return '-'
  }
  
  if (props.formatValue) {
    return props.formatValue(props.value)
  }
  
  // Форматирование по умолчанию
  if (props.unit === '%') {
    return Math.round(props.value).toString()
  }
  if (props.unit === '°C' || props.unit === 'мСм/см') {
    return props.value.toFixed(1)
  }
  if (props.unit === '') {
    return props.value.toFixed(2)
  }
  
  return props.value.toFixed(2)
})

const formatTarget = (target: number): string => {
  return props.formatValue ? props.formatValue(target) : target.toFixed(2)
}

const deviation = computed(() => {
  if (props.value === null || props.target === null || props.target === undefined) {
    return null
  }
  return props.value - props.target
})

const formatDeviation = (dev: number): string => {
  if (props.formatValue) {
    return props.formatValue(Math.abs(dev))
  }
  return Math.abs(dev).toFixed(2)
}

const deviationClass = computed(() => {
  if (deviation.value === null) return ''
  
  const absDev = Math.abs(deviation.value)
  const threshold = props.criticalThreshold || 0.1
  
  if (absDev > threshold * 2) {
    return 'text-[color:var(--accent-red)] font-semibold'
  }
  if (absDev > threshold) {
    return 'text-[color:var(--accent-amber)]'
  }
  return 'text-[color:var(--accent-green)]'
})

const valueColorClass = computed(() => {
  if (deviation.value === null || props.target === null) {
    return 'text-[color:var(--text-primary)]'
  }
  
  const absDev = Math.abs(deviation.value)
  const threshold = props.criticalThreshold || 0.1
  
  if (absDev > threshold * 2) {
    return 'text-[color:var(--accent-red)]'
  }
  if (absDev > threshold) {
    return 'text-[color:var(--accent-amber)]'
  }
  return 'text-[color:var(--accent-green)]'
})

const trendColorClass = computed(() => {
  if (props.trend === null) return ''
  
  if (props.trend > 0) {
    return 'text-[color:var(--accent-green)]'
  }
  if (props.trend < 0) {
    return 'text-[color:var(--accent-red)]'
  }
  return 'text-[color:var(--text-muted)]'
})

const gaugePercentage = computed(() => {
  if (props.value === null || props.target === null || props.target === undefined) {
    return 0
  }
  
  // Процент от целевого значения (ограничиваем 0-100%)
  const percentage = (props.value / props.target) * 100
  return Math.max(0, Math.min(100, percentage))
})

const gaugeColorClass = computed(() => {
  const percentage = gaugePercentage.value
  
  if (percentage >= 90 && percentage <= 110) {
    return 'bg-[color:var(--accent-green)]'
  }
  if (percentage >= 80 && percentage < 90 || percentage > 110 && percentage <= 120) {
    return 'bg-[color:var(--accent-amber)]'
  }
  return 'bg-[color:var(--accent-red)]'
})

const isCritical = computed(() => {
  if (deviation.value === null || props.target === null) {
    return false
  }
  
  const absDev = Math.abs(deviation.value)
  const threshold = props.criticalThreshold || 0.1
  
  return absDev > threshold * 2
})

const sparklineColor = computed(() => {
  // Используем цвет в зависимости от статуса
  switch (props.status) {
    case 'success':
      return 'var(--accent-green)'
    case 'warning':
      return 'var(--accent-amber)'
    case 'danger':
      return 'var(--accent-red)'
    case 'info':
      return 'var(--accent-cyan)'
    default:
      return 'var(--accent-cyan)'
  }
})
</script>

<style scoped>
.metric-indicator-card {
  transition: all 0.2s ease;
}

.metric-indicator-card:hover {
  border-color: var(--border-strong);
}

.metric-indicator-large {
  padding: 1.5rem;
}
</style>

