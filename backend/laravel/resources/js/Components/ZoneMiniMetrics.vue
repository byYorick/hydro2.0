<template>
  <div class="space-y-2">
    <div
      v-for="metric in visibleMetrics"
      :key="metric.key"
      class="flex items-center justify-between text-xs"
    >
      <span class="text-[color:var(--text-muted)]">{{ metric.label }}:</span>
      <div class="flex items-center gap-2">
        <span class="font-semibold text-[color:var(--text-primary)]">{{ metric.value }}</span>
        <span
          v-if="metric.delta !== null && metric.delta !== undefined"
          class="px-1.5 py-0.5 rounded text-[10px] font-medium"
          :class="metric.deltaClass"
        >
          {{ formatDelta(metric.delta) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ZoneTelemetry } from '@/types'
import type { ZoneTargets } from '@/types'

interface PhaseTargets {
  ph?: { min: number; max: number } | null
  ec?: { min: number; max: number } | null
  climate?: { temperature?: number; humidity?: number; co2?: number } | null
}

interface Props {
  telemetry?: ZoneTelemetry | null
  targets?: PhaseTargets | ZoneTargets | null // Поддержка обоих форматов
  showMetrics?: ('all' | 'temperature' | 'humidity' | 'ph' | 'ec' | 'co2')[]
}

const props = withDefaults(defineProps<Props>(), {
  telemetry: null,
  targets: null,
  showMetrics: () => ['all'],
})

interface MetricData {
  key: string
  label: string
  value: string
  delta: number | null
  deltaClass: string
}

const allMetrics = computed((): MetricData[] => {
  const t = props.telemetry || {}
  const tgts = props.targets || {}

  const metrics: MetricData[] = []

  // Проверяем формат targets (новый формат из current_phase или старый ZoneTargets)
  const isNewFormat = 'ph' in tgts || 'ec' in tgts || 'climate' in tgts
  const isOldFormat = 'ph_min' in tgts || 'temp_min' in tgts

  // Проверяем, что telemetry - объект, а не число
  const isTelemetryObject = typeof t === 'object' && t !== null
  const telemetryObj = isTelemetryObject ? t as any : {}

  // Температура
  if (isTelemetryObject && telemetryObj.temperature !== null && telemetryObj.temperature !== undefined) {
    let target: number | null = null
    if (isNewFormat && 'climate' in tgts && tgts.climate?.temperature !== undefined) {
      target = tgts.climate.temperature as number
    } else if (isOldFormat && 'temp_min' in tgts && 'temp_max' in tgts) {
      target = ((tgts as ZoneTargets).temp_min + (tgts as ZoneTargets).temp_max) / 2
    }
    const delta = target !== null ? telemetryObj.temperature - target : null
    metrics.push({
      key: 'temperature',
      label: 'T',
      value: `${telemetryObj.temperature.toFixed(1)}°C`,
      delta,
      deltaClass: getDeltaClass(delta, 2),
    })
  }
  
  // Влажность
  if (isTelemetryObject && telemetryObj.humidity !== null && telemetryObj.humidity !== undefined) {
    let target: number | null = null
    if (isNewFormat && 'climate' in tgts && tgts.climate?.humidity !== undefined) {
      target = tgts.climate.humidity as number
    } else if (isOldFormat && 'humidity_min' in tgts && 'humidity_max' in tgts) {
      target = ((tgts as ZoneTargets).humidity_min + (tgts as ZoneTargets).humidity_max) / 2
    }
    const delta = target !== null ? telemetryObj.humidity - target : null
    metrics.push({
      key: 'humidity',
      label: 'RH',
      value: `${telemetryObj.humidity.toFixed(1)}%`,
      delta,
      deltaClass: getDeltaClass(delta, 5),
    })
  }
  
  // pH
  if (isTelemetryObject && telemetryObj.ph !== null && telemetryObj.ph !== undefined) {
    let target: number | null = null
    if (isNewFormat && 'ph' in tgts && tgts.ph && typeof tgts.ph === 'object' && 'min' in tgts.ph && 'max' in tgts.ph) {
      target = (tgts.ph.min + tgts.ph.max) / 2
    } else if (isOldFormat && 'ph_min' in tgts && 'ph_max' in tgts) {
      target = ((tgts as ZoneTargets).ph_min + (tgts as ZoneTargets).ph_max) / 2
    }
    const delta = target !== null ? telemetryObj.ph - target : null
    metrics.push({
      key: 'ph',
      label: 'pH',
      value: telemetryObj.ph.toFixed(2),
      delta,
      deltaClass: getDeltaClass(delta, 0.2),
    })
  }
  
  // EC
  if (isTelemetryObject && telemetryObj.ec !== null && telemetryObj.ec !== undefined) {
    let target: number | null = null
    if (isNewFormat && 'ec' in tgts && tgts.ec && typeof tgts.ec === 'object' && 'min' in tgts.ec && 'max' in tgts.ec) {
      target = (tgts.ec.min + tgts.ec.max) / 2
    } else if (isOldFormat && 'ec_min' in tgts && 'ec_max' in tgts) {
      target = ((tgts as ZoneTargets).ec_min + (tgts as ZoneTargets).ec_max) / 2
    }
    const delta = target !== null ? telemetryObj.ec - target : null
    metrics.push({
      key: 'ec',
      label: 'EC',
      value: telemetryObj.ec.toFixed(1),
      delta,
      deltaClass: getDeltaClass(delta, 0.2),
    })
  }
  
  // CO2 (если есть в телеметрии)
  if (isTelemetryObject && telemetryObj.co2 !== null && telemetryObj.co2 !== undefined) {
    let target: number | null = null
    if (isNewFormat && 'climate' in tgts && tgts.climate?.co2 !== undefined) {
      target = tgts.climate.co2 as number
    }
    const delta = target !== null ? telemetryObj.co2 - target : null
    metrics.push({
      key: 'co2',
      label: 'CO₂',
      value: `${telemetryObj.co2.toFixed(0)} ppm`,
      delta,
      deltaClass: getDeltaClass(delta, 100),
    })
  }
  
  return metrics
})

const visibleMetrics = computed(() => {
  if (props.showMetrics.includes('all')) {
    return allMetrics.value
  }
  
  return allMetrics.value.filter(m => props.showMetrics.includes(m.key as any))
})

function getDeltaClass(delta: number | null, tolerance: number): string {
  if (delta === null) {
    return 'text-[color:var(--text-dim)] bg-[color:var(--badge-neutral-bg)]'
  }
  
  const absDelta = Math.abs(delta)
  if (absDelta <= tolerance) {
    return 'text-[color:var(--accent-green)] bg-[color:var(--badge-success-bg)]'
  }
  if (absDelta <= tolerance * 2) {
    return 'text-[color:var(--accent-amber)] bg-[color:var(--badge-warning-bg)]'
  }
  return 'text-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]'
}

function formatDelta(delta: number | null): string {
  if (delta === null) return '—'
  
  const sign = delta > 0 ? '+' : ''
  const absValue = Math.abs(delta)
  
  // Форматируем в зависимости от величины
  if (absValue < 0.01) {
    return '±0'
  }
  if (absValue < 1) {
    return `${sign}${absValue.toFixed(2)}`
  }
  return `${sign}${absValue.toFixed(1)}`
}
</script>
