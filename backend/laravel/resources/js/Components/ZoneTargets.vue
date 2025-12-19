<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
    <!-- pH -->
    <Card 
      v-if="targets.ph"
      :class="[
        'transition-all duration-300 hover:border-emerald-300/50 hover:shadow-[0_15px_40px_rgba(48,240,201,0.15)]',
        getCardBorderClass(telemetry.ph, targets.ph.min, targets.ph.max)
      ]"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <div class="text-sm font-medium">pH</div>
          <div 
            v-if="telemetry.ph !== null && telemetry.ph !== undefined"
            :class="[
              'w-2 h-2 rounded-full transition-all duration-300',
              getPulseClass(telemetry.ph, targets.ph.min, targets.ph.max)
            ]"
          />
        </div>
        <Badge :variant="getIndicatorVariant(telemetry.ph, targets.ph.min, targets.ph.max)">
          {{ getIndicatorLabel(telemetry.ph, targets.ph.min, targets.ph.max) }}
        </Badge>
      </div>
      <div 
        :class="[
          'text-2xl font-semibold mt-1 transition-all duration-300',
          getValueColorClass(telemetry.ph, targets.ph.min, targets.ph.max)
        ]"
      >
        {{ formatTelemetryValue(telemetry.ph, 'ph') }}
      </div>
      
      <!-- Прогресс-бар отклонения -->
      <div v-if="telemetry.ph !== null && telemetry.ph !== undefined && targets.ph" class="mt-3">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-neutral-400">Цель: {{ formatTarget(targets.ph) }}</span>
          <span 
            v-if="getDeviationPercent(telemetry.ph, targets.ph) !== null"
            :class="getDeviationColorClass(telemetry.ph, targets.ph.min, targets.ph.max)"
            class="font-medium"
          >
            {{ formatDeviation(telemetry.ph, targets.ph) }}
          </span>
        </div>
        <div class="w-full bg-neutral-800 rounded-full h-1.5 overflow-hidden">
          <div
            :class="getProgressBarClass(telemetry.ph, targets.ph.min, targets.ph.max)"
            class="h-full transition-all duration-500 ease-out"
            :style="{ width: `${getProgressWidth(telemetry.ph, targets.ph)}%` }"
          />
        </div>
      </div>
      <div v-else class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.ph) }}
      </div>
    </Card>

    <!-- EC -->
    <Card 
      v-if="targets.ec"
      :class="[
        'transition-all duration-300 hover:border-cyan-300/50 hover:shadow-[0_15px_40px_rgba(48,240,201,0.15)]',
        getCardBorderClass(telemetry.ec, targets.ec.min, targets.ec.max)
      ]"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <div class="text-sm font-medium">EC</div>
          <div 
            v-if="telemetry.ec !== null && telemetry.ec !== undefined"
            :class="[
              'w-2 h-2 rounded-full transition-all duration-300',
              getPulseClass(telemetry.ec, targets.ec.min, targets.ec.max)
            ]"
          />
        </div>
        <Badge :variant="getIndicatorVariant(telemetry.ec, targets.ec.min, targets.ec.max)">
          {{ getIndicatorLabel(telemetry.ec, targets.ec.min, targets.ec.max) }}
        </Badge>
      </div>
      <div 
        :class="[
          'text-2xl font-semibold mt-1 transition-all duration-300',
          getValueColorClass(telemetry.ec, targets.ec.min, targets.ec.max)
        ]"
      >
        {{ formatTelemetryValue(telemetry.ec, 'ec') }}
      </div>
      
      <!-- Прогресс-бар отклонения -->
      <div v-if="telemetry.ec !== null && telemetry.ec !== undefined && targets.ec" class="mt-3">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-neutral-400">Цель: {{ formatTarget(targets.ec) }}</span>
          <span 
            v-if="getDeviationPercent(telemetry.ec, targets.ec) !== null"
            :class="getDeviationColorClass(telemetry.ec, targets.ec.min, targets.ec.max)"
            class="font-medium"
          >
            {{ formatDeviation(telemetry.ec, targets.ec) }}
          </span>
        </div>
        <div class="w-full bg-neutral-800 rounded-full h-1.5 overflow-hidden">
          <div
            :class="getProgressBarClass(telemetry.ec, targets.ec.min, targets.ec.max)"
            class="h-full transition-all duration-500 ease-out"
            :style="{ width: `${getProgressWidth(telemetry.ec, targets.ec)}%` }"
          />
        </div>
      </div>
      <div v-else class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.ec) }}
      </div>
    </Card>

    <!-- Temperature -->
    <Card 
      v-if="targets.temp"
      :class="[
        'transition-all duration-300 hover:border-amber-300/50 hover:shadow-[0_15px_40px_rgba(245,159,69,0.15)]',
        getCardBorderClass(telemetry.temperature, targets.temp.min, targets.temp.max)
      ]"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <div class="text-sm font-medium">Температура</div>
          <div 
            v-if="telemetry.temperature !== null && telemetry.temperature !== undefined"
            :class="[
              'w-2 h-2 rounded-full transition-all duration-300',
              getPulseClass(telemetry.temperature, targets.temp.min, targets.temp.max)
            ]"
          />
        </div>
        <Badge :variant="getIndicatorVariant(telemetry.temperature, targets.temp.min, targets.temp.max)">
          {{ getIndicatorLabel(telemetry.temperature, targets.temp.min, targets.temp.max) }}
        </Badge>
      </div>
      <div 
        :class="[
          'text-2xl font-semibold mt-1 transition-all duration-300',
          getValueColorClass(telemetry.temperature, targets.temp.min, targets.temp.max)
        ]"
      >
        {{ formatTelemetryValue(telemetry.temperature, 'temp', '°C') }}
      </div>
      
      <!-- Прогресс-бар отклонения -->
      <div v-if="telemetry.temperature !== null && telemetry.temperature !== undefined && targets.temp" class="mt-3">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-neutral-400">Цель: {{ formatTarget(targets.temp, '°C') }}</span>
          <span 
            v-if="getDeviationPercent(telemetry.temperature, targets.temp) !== null"
            :class="getDeviationColorClass(telemetry.temperature, targets.temp.min, targets.temp.max)"
            class="font-medium"
          >
            {{ formatDeviation(telemetry.temperature, targets.temp, '°C') }}
          </span>
        </div>
        <div class="w-full bg-neutral-800 rounded-full h-1.5 overflow-hidden">
          <div
            :class="getProgressBarClass(telemetry.temperature, targets.temp.min, targets.temp.max)"
            class="h-full transition-all duration-500 ease-out"
            :style="{ width: `${getProgressWidth(telemetry.temperature, targets.temp)}%` }"
          />
        </div>
      </div>
      <div v-else class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.temp, '°C') }}
      </div>
    </Card>

    <!-- Humidity -->
    <Card 
      v-if="targets.humidity"
      :class="[
        'transition-all duration-300 hover:border-cyan-200/50 hover:shadow-[0_15px_40px_rgba(48,240,201,0.15)]',
        getCardBorderClass(telemetry.humidity, targets.humidity.min, targets.humidity.max)
      ]"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <div class="text-sm font-medium">Влажность</div>
          <div 
            v-if="telemetry.humidity !== null && telemetry.humidity !== undefined"
            :class="[
              'w-2 h-2 rounded-full transition-all duration-300',
              getPulseClass(telemetry.humidity, targets.humidity.min, targets.humidity.max)
            ]"
          />
        </div>
        <Badge :variant="getIndicatorVariant(telemetry.humidity, targets.humidity.min, targets.humidity.max)">
          {{ getIndicatorLabel(telemetry.humidity, targets.humidity.min, targets.humidity.max) }}
        </Badge>
      </div>
      <div 
        :class="[
          'text-2xl font-semibold mt-1 transition-all duration-300',
          getValueColorClass(telemetry.humidity, targets.humidity.min, targets.humidity.max)
        ]"
      >
        {{ formatTelemetryValue(telemetry.humidity, 'humidity', '%') }}
      </div>
      
      <!-- Прогресс-бар отклонения -->
      <div v-if="telemetry.humidity !== null && telemetry.humidity !== undefined && targets.humidity" class="mt-3">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-neutral-400">Цель: {{ formatTarget(targets.humidity, '%') }}</span>
          <span 
            v-if="getDeviationPercent(telemetry.humidity, targets.humidity) !== null"
            :class="getDeviationColorClass(telemetry.humidity, targets.humidity.min, targets.humidity.max)"
            class="font-medium"
          >
            {{ formatDeviation(telemetry.humidity, targets.humidity, '%') }}
          </span>
        </div>
        <div class="w-full bg-neutral-800 rounded-full h-1.5 overflow-hidden">
          <div
            :class="getProgressBarClass(telemetry.humidity, targets.humidity.min, targets.humidity.max)"
            class="h-full transition-all duration-500 ease-out"
            :style="{ width: `${getProgressWidth(telemetry.humidity, targets.humidity)}%` }"
          />
        </div>
      </div>
      <div v-else class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.humidity, '%') }}
      </div>
    </Card>
  </div>
</template>

<script setup lang="ts">
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import type { ZoneTelemetry, ZoneTargets } from '@/types'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  telemetry?: ZoneTelemetry
  targets?: Partial<ZoneTargets> & {
    ph?: { min?: number; max?: number; target?: number }
    ec?: { min?: number; max?: number; target?: number }
    temp?: { min?: number; max?: number; target?: number }
    humidity?: { min?: number; max?: number; target?: number }
  }
}

const props = withDefaults(defineProps<Props>(), {
  telemetry: () => ({ ph: null, ec: null, temperature: null, humidity: null }),
  targets: () => ({})
})

// Вычисляем индикатор (зеленый/желтый/красный)
function getIndicatorVariant(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): BadgeVariant {
  if (value === null || value === undefined) return 'neutral'
  if (min === null || max === null) return 'info'
  
  const target = (min + max) / 2
  const tolerance = (max - min) * 0.1 // 10% от диапазона
  
  if (value >= min && value <= max) return 'success'
  if (value >= min - tolerance && value <= max + tolerance) return 'warning'
  return 'danger'
}

function getIndicatorLabel(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  if (value === null || value === undefined) return 'Нет данных'
  if (min === null || max === null) return 'OK'
  
  if (value >= min && value <= max) return 'OK'
  if (value < min) return 'Низкий'
  return 'Высокий'
}

// Форматирование значений телеметрии
function trimTrailingZeros(value: string): string {
  if (!value.includes('.')) {
    return value
  }

  return value.replace(/(\.\d*?[1-9])0+$/u, '$1').replace(/\.0+$/u, '')
}

function formatTelemetryValue(value: number | null | undefined, type: string, unit: string = ''): string {
  if (value === null || value === undefined) return '-'
  if (typeof value !== 'number') return String(value)
  
  // Для pH показываем 2 знака после точки, для остальных - 1
  const decimals = type === 'ph' ? 2 : 1
  const fixed = value.toFixed(decimals)
  const formatted = type === 'ph' ? fixed : trimTrailingZeros(fixed)
  
  return unit ? `${formatted}${unit}` : formatted
}

// Форматирование целей
function formatTarget(target: { min?: number | null; max?: number | null; target?: number | null } | undefined, unit: string = ''): string {
  if (!target) return '-'
  
  if (target.target !== null && target.target !== undefined) {
    const decimals = unit === '' ? 2 : 1 // pH без единиц - 2 знака, остальные - 1
    const fixed = Number(target.target).toFixed(decimals)
    const formatted = unit === '' ? fixed : trimTrailingZeros(fixed)
    return `${formatted}${unit}`
  }
  
  if (target.min !== null && target.max !== null && target.min !== undefined && target.max !== undefined) {
    const decimals = unit === '' ? 2 : 1
    const minFormatted = unit === '' ? Number(target.min).toFixed(decimals) : trimTrailingZeros(Number(target.min).toFixed(decimals))
    const maxFormatted = unit === '' ? Number(target.max).toFixed(decimals) : trimTrailingZeros(Number(target.max).toFixed(decimals))
    return `${minFormatted}–${maxFormatted}${unit}`
  }
  
  return '-'
}

// Вычисление процента отклонения
function getDeviationPercent(value: number | null | undefined, target: { min?: number | null; max?: number | null; target?: number | null }): number | null {
  if (value === null || value === undefined || !target) return null
  
  const targetValue = target.target !== null && target.target !== undefined 
    ? target.target 
    : (target.min !== null && target.max !== null && target.min !== undefined && target.max !== undefined)
      ? (target.min + target.max) / 2
      : null
  
  if (targetValue === null) return null
  
  const deviation = ((value - targetValue) / targetValue) * 100
  return deviation
}

// Форматирование отклонения
function formatDeviation(value: number | null | undefined, target: { min?: number | null; max?: number | null; target?: number | null }, unit: string = ''): string {
  const percent = getDeviationPercent(value, target)
  if (percent === null) return ''
  
  const sign = percent > 0 ? '+' : ''
  return `${sign}${percent.toFixed(1)}%`
}

// Вычисление ширины прогресс-бара (0-100%)
function getProgressWidth(value: number | null | undefined, target: { min?: number | null; max?: number | null; target?: number | null }): number {
  if (value === null || value === undefined || !target) return 0
  
  if (target.target !== null && target.target !== undefined) {
    // Если есть целевое значение, показываем отклонение от него
    const deviation = Math.abs(value - target.target)
    const range = target.min !== null && target.max !== null ? (target.max - target.min) : 1
    const normalized = Math.min(deviation / (range * 0.5), 1) * 100
    return normalized
  }
  
  if (target.min !== null && target.max !== null && target.min !== undefined && target.max !== undefined) {
    // Если есть диапазон, показываем позицию в диапазоне
    const range = target.max - target.min
    const extendedMin = target.min - range * 0.2
    const extendedMax = target.max + range * 0.2
    const extendedRange = extendedMax - extendedMin
    
    if (value < extendedMin) return 0
    if (value > extendedMax) return 100
    
    const position = ((value - extendedMin) / extendedRange) * 100
    return Math.max(0, Math.min(100, position))
  }
  
  return 50 // По умолчанию центр
}

// Классы для прогресс-бара
function getProgressBarClass(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  const variant = getIndicatorVariant(value, min, max)
  switch (variant) {
    case 'success':
      return 'bg-emerald-500'
    case 'warning':
      return 'bg-amber-500'
    case 'danger':
      return 'bg-red-500'
    default:
      return 'bg-neutral-500'
  }
}

// Классы для цвета значения
function getValueColorClass(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  const variant = getIndicatorVariant(value, min, max)
  switch (variant) {
    case 'success':
      return 'text-emerald-400'
    case 'warning':
      return 'text-amber-400'
    case 'danger':
      return 'text-red-400'
    default:
      return 'text-neutral-300'
  }
}

// Классы для цвета отклонения
function getDeviationColorClass(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  const variant = getIndicatorVariant(value, min, max)
  switch (variant) {
    case 'success':
      return 'text-emerald-400'
    case 'warning':
      return 'text-amber-400'
    case 'danger':
      return 'text-red-400'
    default:
      return 'text-neutral-400'
  }
}

// Классы для границы карточки
function getCardBorderClass(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  const variant = getIndicatorVariant(value, min, max)
  switch (variant) {
    case 'success':
      return 'border-emerald-700/30'
    case 'warning':
      return 'border-amber-700/30'
    case 'danger':
      return 'border-red-700/30'
    default:
      return ''
  }
}

// Классы для пульсирующего индикатора
function getPulseClass(value: number | null | undefined, min: number | null | undefined, max: number | null | undefined): string {
  const variant = getIndicatorVariant(value, min, max)
  switch (variant) {
    case 'success':
      return 'bg-emerald-500 animate-pulse'
    case 'warning':
      return 'bg-amber-500 animate-pulse'
    case 'danger':
      return 'bg-red-500 animate-pulse'
    default:
      return 'bg-neutral-500'
  }
}
</script>
