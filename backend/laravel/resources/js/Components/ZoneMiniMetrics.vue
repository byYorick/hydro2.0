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
import type { ZoneTelemetry, ZoneTargets } from '@/types'

type ClimateTargets = {
  temperature?: number
  humidity?: number
  co2?: number
}

interface PhaseTargets {
  ph?: { min: number; max: number } | null
  ec?: { min: number; max: number } | null
  climate?: ClimateTargets | null
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

const isPhaseTargets = (
  targets: PhaseTargets | ZoneTargets | null | undefined
): targets is PhaseTargets => {
  return !!targets && typeof targets === 'object' && (
    'ph' in targets || 'ec' in targets || 'climate' in targets
  )
}

const isLegacyTargets = (
  targets: PhaseTargets | ZoneTargets | null | undefined
): targets is ZoneTargets => {
  return !!targets && typeof targets === 'object' && (
    'ph_min' in targets || 'temp_min' in targets || 'humidity_min' in targets || 'ec_min' in targets
  )
}

interface MetricData {
  key: string
  label: string
  value: string
  delta: number | null
  deltaClass: string
}

const allMetrics = computed((): MetricData[] => {
  const t = props.telemetry || {}
  const targets = props.targets

  const metrics: MetricData[] = []

  // Проверяем, что telemetry - объект, а не число
  const isTelemetryObject = typeof t === 'object' && t !== null
  const telemetryObj = isTelemetryObject ? (t as ZoneTelemetry) : ({} as ZoneTelemetry)
  const phaseTargets = isPhaseTargets(targets) ? targets : null
  const legacyTargets = isLegacyTargets(targets) ? targets : null
  const climateTargets = phaseTargets?.climate && typeof phaseTargets.climate === 'object'
    ? phaseTargets.climate
    : null

  // Температура
  if (isTelemetryObject && telemetryObj.temperature !== null && telemetryObj.temperature !== undefined) {
    let target: number | null = null
    if (climateTargets?.temperature !== undefined) {
      target = climateTargets.temperature
    } else if (legacyTargets?.temp_min !== undefined && legacyTargets?.temp_max !== undefined) {
      target = (legacyTargets.temp_min + legacyTargets.temp_max) / 2
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
    if (climateTargets?.humidity !== undefined) {
      target = climateTargets.humidity
    } else if (legacyTargets?.humidity_min !== undefined && legacyTargets?.humidity_max !== undefined) {
      target = (legacyTargets.humidity_min + legacyTargets.humidity_max) / 2
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
    const phTargets = phaseTargets?.ph && typeof phaseTargets.ph === 'object' ? phaseTargets.ph : null
    if (phTargets?.min !== undefined && phTargets?.max !== undefined) {
      target = (phTargets.min + phTargets.max) / 2
    } else if (legacyTargets?.ph_min !== undefined && legacyTargets?.ph_max !== undefined) {
      target = (legacyTargets.ph_min + legacyTargets.ph_max) / 2
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
    const ecTargets = phaseTargets?.ec && typeof phaseTargets.ec === 'object' ? phaseTargets.ec : null
    if (ecTargets?.min !== undefined && ecTargets?.max !== undefined) {
      target = (ecTargets.min + ecTargets.max) / 2
    } else if (legacyTargets?.ec_min !== undefined && legacyTargets?.ec_max !== undefined) {
      target = (legacyTargets.ec_min + legacyTargets.ec_max) / 2
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
    if (climateTargets?.co2 !== undefined) {
      target = climateTargets.co2
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
