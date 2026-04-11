<template>
  <div class="metric-pill">
    <div class="flex items-baseline justify-between gap-2">
      <span class="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
        {{ label }}
      </span>
      <span
        v-if="offline"
        class="inline-flex items-center gap-1 rounded-full border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] px-1.5 py-0.5 text-[9px] font-medium text-[color:var(--badge-danger-text)]"
      >
        <span aria-hidden="true">📡</span>
        offline
      </span>
    </div>

    <div class="mt-0.5 flex items-baseline gap-1">
      <span
        class="text-xl font-semibold tabular-nums leading-none"
        :class="offline ? 'text-[color:var(--text-dim)]' : valueColorClass"
      >
        {{ offline ? '—' : formattedValue }}
      </span>
      <span
        v-if="unit && !offline && value !== null"
        class="text-[10px] text-[color:var(--text-muted)]"
      >
        {{ unit }}
      </span>
    </div>

    <div class="mt-1.5 relative h-1.5 w-full rounded-full bg-[color:var(--border-muted)]">
      <!-- Target zone (green) -->
      <div
        v-if="targetZoneStyle"
        class="absolute inset-y-0 rounded-full bg-[color:var(--accent-green)]/35"
        :style="targetZoneStyle"
      ></div>
      <!-- Marker -->
      <div
        v-if="markerStyle"
        class="absolute top-1/2 h-2.5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full"
        :class="markerColorClass"
        :style="markerStyle"
      ></div>
    </div>

    <div class="mt-1 text-[9px] text-[color:var(--text-dim)] tabular-nums">
      {{ rangeLabel }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  value: number | null
  targetMin: number | null
  targetMax: number | null
  /** Общий диапазон оси (например 0..14 для pH). Если не задан — выводится из target ±20%. */
  axisMin?: number | null
  axisMax?: number | null
  unit?: string
  decimals?: number
  offline?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  axisMin: null,
  axisMax: null,
  unit: '',
  decimals: 2,
  offline: false,
})

const formattedValue = computed(() => {
  if (props.value === null || Number.isNaN(props.value)) return '—'
  return props.value.toFixed(props.decimals)
})

const axisBounds = computed(() => {
  if (props.axisMin !== null && props.axisMax !== null) {
    return { min: props.axisMin, max: props.axisMax }
  }
  if (props.targetMin !== null && props.targetMax !== null) {
    const span = Math.max(0.1, props.targetMax - props.targetMin)
    return {
      min: props.targetMin - span * 1.5,
      max: props.targetMax + span * 1.5,
    }
  }
  return { min: 0, max: 1 }
})

function normalize(value: number): number {
  const { min, max } = axisBounds.value
  if (max === min) return 0.5
  return Math.max(0, Math.min(1, (value - min) / (max - min)))
}

const targetZoneStyle = computed(() => {
  if (props.targetMin === null || props.targetMax === null) return null
  const left = normalize(props.targetMin) * 100
  const right = normalize(props.targetMax) * 100
  const width = Math.max(0, right - left)
  return { left: `${left}%`, width: `${width}%` }
})

const markerStyle = computed(() => {
  if (props.value === null || Number.isNaN(props.value)) return null
  const pos = normalize(props.value) * 100
  return { left: `${pos}%` }
})

const state = computed<'ok' | 'warn' | 'danger' | 'unknown'>(() => {
  if (props.offline) return 'danger'
  if (props.value === null || Number.isNaN(props.value)) return 'unknown'
  if (props.targetMin === null || props.targetMax === null) return 'unknown'
  if (props.value >= props.targetMin && props.value <= props.targetMax) return 'ok'
  const span = Math.max(0.1, props.targetMax - props.targetMin)
  const tolerance = span * 0.25
  if (
    props.value >= props.targetMin - tolerance
    && props.value <= props.targetMax + tolerance
  ) {
    return 'warn'
  }
  return 'danger'
})

const valueColorClass = computed(() => {
  switch (state.value) {
    case 'ok': return 'text-[color:var(--accent-green)]'
    case 'warn': return 'text-[color:var(--accent-amber)]'
    case 'danger': return 'text-[color:var(--accent-red)]'
    default: return 'text-[color:var(--text-primary)]'
  }
})

const markerColorClass = computed(() => {
  switch (state.value) {
    case 'ok': return 'bg-[color:var(--accent-green)]'
    case 'warn': return 'bg-[color:var(--accent-amber)]'
    case 'danger': return 'bg-[color:var(--accent-red)]'
    default: return 'bg-[color:var(--text-primary)]'
  }
})

const rangeLabel = computed(() => {
  if (props.targetMin === null || props.targetMax === null) return '—'
  const d = props.decimals
  return `${props.targetMin.toFixed(d)}–${props.targetMax.toFixed(d)}${props.unit ? ' ' + props.unit.trim() : ''}`
})
</script>

<style scoped>
.metric-pill {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
