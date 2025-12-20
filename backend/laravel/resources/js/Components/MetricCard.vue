<template>
  <Card 
    class="relative overflow-hidden hover:border-[color:var(--border-strong)] transition-all duration-200 hover:shadow-[var(--shadow-card)] group"
    :data-testid="$attrs['data-testid']"
  >
    <!-- Фоновый градиент для визуального акцента -->
    <div 
      class="absolute inset-0 opacity-5 group-hover:opacity-10 transition-opacity"
      :style="{ background: `linear-gradient(135deg, ${color} 0%, transparent 100%)` }"
    ></div>
    
    <div class="relative">
      <!-- Заголовок с иконкой -->
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <div 
            class="w-10 h-10 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110"
            :style="{ 
              backgroundColor: `${color}20`,
              borderColor: `${color}40`,
              borderWidth: '1px',
              borderStyle: 'solid'
            }"
          >
            <slot name="icon">
              <svg class="w-5 h-5" :style="{ color: color }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </slot>
          </div>
          <div>
            <div class="text-xs font-medium uppercase tracking-wide text-[color:var(--text-muted)] group-hover:text-[color:var(--text-primary)] transition-colors">
              {{ label }}
            </div>
            <div v-if="subtitle" class="text-xs text-[color:var(--text-dim)] mt-0.5">
              {{ subtitle }}
            </div>
          </div>
        </div>
        <!-- Индикатор статуса -->
        <div 
          v-if="status !== 'neutral'"
          class="w-2 h-2 rounded-full animate-pulse"
          :class="{
            'bg-[color:var(--accent-green)]': status === 'success',
            'bg-[color:var(--accent-amber)]': status === 'warning',
            'bg-[color:var(--accent-red)]': status === 'danger',
            'bg-[color:var(--accent-cyan)]': status === 'info',
          }"
        ></div>
      </div>

      <!-- Основное значение -->
      <div class="mb-3">
        <div 
          class="text-4xl font-bold mb-1 transition-colors"
          :style="{ color: color }"
        >
          {{ formattedValue }}
          <span v-if="unit" class="text-2xl text-[color:var(--text-muted)] ml-1">{{ unit }}</span>
        </div>
        
        <!-- Тренд и изменение -->
        <div v-if="trend !== null" class="flex items-center gap-2 text-sm">
          <div 
            class="flex items-center gap-1 font-medium"
            :class="trend > 0 ? 'text-[color:var(--accent-green)]' : trend < 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-dim)]'"
          >
            <svg 
              v-if="trend > 0" 
              class="w-4 h-4" 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            <svg 
              v-else-if="trend < 0" 
              class="w-4 h-4" 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
            </svg>
            <svg 
              v-else 
              class="w-4 h-4" 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14" />
            </svg>
            <span>{{ Math.abs(trend).toFixed(decimals) }}</span>
          </div>
          <span v-if="trendLabel" class="text-[color:var(--text-dim)] text-xs">{{ trendLabel }}</span>
        </div>
      </div>

      <!-- Прогресс-бар для целевых значений -->
      <div v-if="target !== null && target.min !== undefined && target.max !== undefined" class="mb-2">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-[color:var(--text-muted)]">Цель: {{ target.min }}-{{ target.max }}</span>
          <span 
            class="font-medium"
            :class="isInTarget ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-amber)]'"
          >
            {{ isInTarget ? '✓ В норме' : '⚠ Вне нормы' }}
          </span>
        </div>
        <div class="h-2 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
          <div 
            class="h-full transition-all duration-300 rounded-full"
            :class="progressBarClass"
            :style="{ width: `${progressPercentage}%` }"
          ></div>
        </div>
        <div class="flex items-center justify-between text-xs mt-1 text-[color:var(--text-dim)]">
          <span>{{ target.min }}</span>
          <span>{{ target.max }}</span>
        </div>
      </div>

      <!-- Дополнительная информация -->
      <div v-if="$slots.footer" class="mt-3 pt-3 border-t border-[color:var(--border-muted)]">
        <slot name="footer"></slot>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'

interface Target {
  min: number
  max: number
}

interface Props {
  label: string
  value: number | null | undefined
  unit?: string
  color?: string
  status?: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  trend?: number | null
  trendLabel?: string
  target?: Target | null
  subtitle?: string
  decimals?: number
}

const props = withDefaults(defineProps<Props>(), {
  color: '#3b82f6',
  status: 'neutral',
  trend: null,
  target: null,
  decimals: 2,
})

const formattedValue = computed(() => {
  if (props.value === null || props.value === undefined) return '-'
  return props.value.toFixed(props.decimals)
})

const isInTarget = computed(() => {
  if (!props.target || props.value === null || props.value === undefined) return true
  const { min, max } = props.target
  return props.value >= min && props.value <= max
})

const progressPercentage = computed(() => {
  if (!props.target || props.value === null || props.value === undefined) return 0
  const { min, max } = props.target
  const range = max - min
  if (range === 0) return 50
  
  // Нормализуем значение в диапазоне 0-100%
  const normalized = ((props.value - min) / range) * 100
  return Math.max(0, Math.min(100, normalized))
})

const progressBarClass = computed(() => {
  if (isInTarget.value) {
    return 'bg-[color:var(--accent-green)]'
  }
  // Если значение ниже минимума
  if (props.value !== null && props.value !== undefined && props.target) {
    if (props.value < props.target.min) {
      return 'bg-[color:var(--accent-cyan)]'
    }
    // Если значение выше максимума
    if (props.value > props.target.max) {
      return 'bg-[color:var(--accent-red)]'
    }
  }
  return 'bg-[color:var(--accent-amber)]'
})
</script>





