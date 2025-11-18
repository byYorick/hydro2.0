<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
    <!-- pH -->
    <Card v-if="targets.ph">
      <div class="flex items-center justify-between mb-1">
        <div class="text-sm font-medium">pH</div>
        <Badge :variant="getIndicatorVariant(telemetry.ph, targets.ph.min, targets.ph.max)">
          {{ getIndicatorLabel(telemetry.ph, targets.ph.min, targets.ph.max) }}
        </Badge>
      </div>
      <div class="text-2xl font-semibold mt-1">{{ formatTelemetryValue(telemetry.ph, 'ph') }}</div>
      <div class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.ph) }}
      </div>
    </Card>

    <!-- EC -->
    <Card v-if="targets.ec">
      <div class="flex items-center justify-between mb-1">
        <div class="text-sm font-medium">EC</div>
        <Badge :variant="getIndicatorVariant(telemetry.ec, targets.ec.min, targets.ec.max)">
          {{ getIndicatorLabel(telemetry.ec, targets.ec.min, targets.ec.max) }}
        </Badge>
      </div>
      <div class="text-2xl font-semibold mt-1">{{ formatTelemetryValue(telemetry.ec, 'ec') }}</div>
      <div class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.ec) }}
      </div>
    </Card>

    <!-- Temperature -->
    <Card v-if="targets.temp">
      <div class="flex items-center justify-between mb-1">
        <div class="text-sm font-medium">Температура</div>
        <Badge :variant="getIndicatorVariant(telemetry.temperature, targets.temp.min, targets.temp.max)">
          {{ getIndicatorLabel(telemetry.temperature, targets.temp.min, targets.temp.max) }}
        </Badge>
      </div>
      <div class="text-2xl font-semibold mt-1">{{ formatTelemetryValue(telemetry.temperature, 'temp', '°C') }}</div>
      <div class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.temp, '°C') }}
      </div>
    </Card>

    <!-- Humidity -->
    <Card v-if="targets.humidity">
      <div class="flex items-center justify-between mb-1">
        <div class="text-sm font-medium">Влажность</div>
        <Badge :variant="getIndicatorVariant(telemetry.humidity, targets.humidity.min, targets.humidity.max)">
          {{ getIndicatorLabel(telemetry.humidity, targets.humidity.min, targets.humidity.max) }}
        </Badge>
      </div>
      <div class="text-2xl font-semibold mt-1">{{ formatTelemetryValue(telemetry.humidity, 'humidity', '%') }}</div>
      <div class="text-xs text-neutral-400 mt-1">
        Цель: {{ formatTarget(targets.humidity, '%') }}
      </div>
    </Card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'

const props = defineProps({
  telemetry: {
    type: Object,
    default: () => ({ ph: null, ec: null, temperature: null, humidity: null }),
  },
  targets: {
    type: Object,
    default: () => ({}),
  },
})

// Вычисляем индикатор (зеленый/желтый/красный)
function getIndicatorVariant(value, min, max) {
  if (value === null || value === undefined) return 'neutral'
  if (min === null || max === null) return 'info'
  
  const target = (min + max) / 2
  const tolerance = (max - min) * 0.1 // 10% от диапазона
  
  if (value >= min && value <= max) return 'success'
  if (value >= min - tolerance && value <= max + tolerance) return 'warning'
  return 'danger'
}

function getIndicatorLabel(value, min, max) {
  if (value === null || value === undefined) return 'Нет данных'
  if (min === null || max === null) return 'OK'
  
  if (value >= min && value <= max) return 'OK'
  if (value < min) return 'Низкий'
  return 'Высокий'
}

// Форматирование значений телеметрии
function formatTelemetryValue(value, type, unit = '') {
  if (value === null || value === undefined) return '-'
  if (typeof value !== 'number') return value
  
  // Для pH показываем 2 знака после точки, для остальных - 1
  const decimals = type === 'ph' ? 2 : 1
  const formatted = value.toFixed(decimals)
  
  return unit ? `${formatted}${unit}` : formatted
}

// Форматирование целей
function formatTarget(target, unit = '') {
  if (!target) return '-'
  
  if (target.target !== null && target.target !== undefined) {
    const decimals = unit === '' ? 2 : 1 // pH без единиц - 2 знака, остальные - 1
    return `${Number(target.target).toFixed(decimals)}${unit}`
  }
  
  if (target.min !== null && target.max !== null) {
    const decimals = unit === '' ? 2 : 1
    return `${Number(target.min).toFixed(decimals)}–${Number(target.max).toFixed(decimals)}${unit}`
  }
  
  return '-'
}
</script>

