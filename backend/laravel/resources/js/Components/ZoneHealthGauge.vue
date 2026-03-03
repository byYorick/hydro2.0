<template>
  <div class="flex flex-col items-center gap-1.5">
    <div class="relative">
      <svg
        :width="svgW"
        :height="svgH"
        :viewBox="`0 0 ${svgW} ${svgH}`"
        class="overflow-visible"
        :aria-label="`${label}: ${displayValue}`"
      >
        <!-- Track: gray background arc -->
        <path
          :d="fullTrackPath"
          fill="none"
          stroke="var(--border-muted)"
          :stroke-width="TRACK_W"
          stroke-linecap="round"
        />

        <!-- Target range highlight -->
        <path
          v-if="targetRangeArcPath"
          :d="targetRangeArcPath"
          fill="none"
          :stroke="statusColor"
          :stroke-width="TRACK_W"
          stroke-linecap="round"
          opacity="0.25"
        />

        <!-- Value arc (filled up to current value) -->
        <path
          v-if="valueArcPath"
          :d="valueArcPath"
          fill="none"
          :stroke="statusColor"
          :stroke-width="TRACK_W"
          stroke-linecap="round"
        />

        <!-- Value dot indicator -->
        <circle
          v-if="hasValue && valueDot"
          :cx="valueDot.x"
          :cy="valueDot.y"
          :r="DOT_R"
          :fill="statusColor"
          class="transition-all duration-500 ease-out"
          :style="{ filter: `drop-shadow(0 0 3px ${statusColor})` }"
        />

        <!-- End-of-range min/max ticks -->
        <line
          :x1="leftEnd.x - 1"
          :y1="leftEnd.y"
          :x2="leftEnd.x + 1"
          :y2="leftEnd.y"
          stroke="var(--text-dim)"
          stroke-width="1"
        />
        <line
          :x1="rightEnd.x - 1"
          :y1="rightEnd.y"
          :x2="rightEnd.x + 1"
          :y2="rightEnd.y"
          stroke="var(--text-dim)"
          stroke-width="1"
        />
      </svg>

      <!-- Status icon (top-right corner) -->
      <div
        v-if="hasValue"
        class="absolute top-0 right-0 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold"
        :class="statusBgClass"
      >
        {{ statusIcon }}
      </div>
    </div>

    <!-- Metric value display -->
    <div class="text-center leading-none">
      <div
        class="text-xl font-bold leading-none tabular-nums"
        :style="{ color: hasValue ? statusColor : 'var(--text-dim)' }"
      >
        {{ displayValue }}
      </div>
      <div class="text-[9px] text-[color:var(--text-dim)] mt-0.5 tracking-wide uppercase">
        {{ label }}
        <span v-if="unit">{{ unit }}</span>
      </div>
      <div
        v-if="hasTargets"
        class="text-[8px] text-[color:var(--text-dim)] mt-0.5"
      >
        {{ fmt(targetMin) }}–{{ fmt(targetMax) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  value?: number | null
  targetMin?: number | null
  targetMax?: number | null
  globalMin?: number
  globalMax?: number
  label?: string
  unit?: string
  decimals?: number
}

const props = withDefaults(defineProps<Props>(), {
  globalMin: undefined,
  globalMax: undefined,
  decimals: 2,
  label: '',
  unit: '',
})

// ─── SVG geometry ────────────────────────────────────────────────────────────
const svgW = 84
const svgH = 50
const CX = svgW / 2      // 42
const CY = svgH - 4      // 46  — anchor near bottom
const R = 38             // arc radius
const TRACK_W = 5
const DOT_R = 5.5

// ─── Derived ranges ───────────────────────────────────────────────────────────
const globalMin = computed(() => {
  if (props.globalMin !== undefined) return props.globalMin
  // Auto-range: expand 30% beyond target
  if (props.targetMin != null && props.targetMax != null) {
    const span = props.targetMax - props.targetMin
    return props.targetMin - span * 0.5
  }
  return 0
})

const globalMax = computed(() => {
  if (props.globalMax !== undefined) return props.globalMax
  if (props.targetMin != null && props.targetMax != null) {
    const span = props.targetMax - props.targetMin
    return props.targetMax + span * 0.5
  }
  return 10
})

const targetMin = computed(() => props.targetMin ?? null)
const targetMax = computed(() => props.targetMax ?? null)
const hasTargets = computed(() => targetMin.value !== null && targetMax.value !== null)
const hasValue = computed(() => props.value !== null && props.value !== undefined)

// ─── Status computation ───────────────────────────────────────────────────────
const status = computed((): 'ok' | 'warning' | 'danger' | 'neutral' => {
  if (!hasValue.value || props.value == null) return 'neutral'
  if (!hasTargets.value || targetMin.value == null || targetMax.value == null) return 'neutral'
  const v = props.value
  const lo = targetMin.value
  const hi = targetMax.value
  const span = hi - lo
  if (v >= lo && v <= hi) return 'ok'
  const margin = span * 0.2 // 20% tolerance
  if (v >= lo - margin && v <= hi + margin) return 'warning'
  return 'danger'
})

const statusColor = computed(() => {
  switch (status.value) {
    case 'ok': return 'var(--accent-green)'
    case 'warning': return 'var(--accent-amber)'
    case 'danger': return 'var(--accent-red)'
    default: return 'var(--text-dim)'
  }
})

const statusIcon = computed(() => {
  switch (status.value) {
    case 'ok': return '✓'
    case 'warning': return '!'
    case 'danger': return '✕'
    default: return ''
  }
})

const statusBgClass = computed(() => {
  switch (status.value) {
    case 'ok': return 'bg-[color:var(--badge-success-bg)] text-[color:var(--accent-green)]'
    case 'warning': return 'bg-[color:var(--badge-warning-bg)] text-[color:var(--accent-amber)]'
    case 'danger': return 'bg-[color:var(--badge-danger-bg)] text-[color:var(--accent-red)]'
    default: return ''
  }
})

// ─── Arc math ─────────────────────────────────────────────────────────────────
// Maps a value in [globalMin, globalMax] to a percentage [0, 1]
function valueToPct(v: number): number {
  const range = globalMax.value - globalMin.value
  if (range === 0) return 0
  return Math.max(0, Math.min(1, (v - globalMin.value) / range))
}

// Maps pct [0,1] to a point on the ∩ semicircle arc
// pct=0 → left end, pct=0.5 → top, pct=1 → right end
function pctToPoint(pct: number): { x: number; y: number } {
  const angle = Math.PI * (1 - pct) // π → 0
  return {
    x: +(CX + R * Math.cos(angle)).toFixed(2),
    y: +(CY - R * Math.sin(angle)).toFixed(2),
  }
}

// Builds an SVG arc path from pct1 to pct2 along the ∩ semicircle
function arcPath(pct1: number, pct2: number): string {
  if (Math.abs(pct2 - pct1) < 0.001) return ''
  const p1 = pctToPoint(pct1)
  const p2 = pctToPoint(pct2)
  const sweep = (pct2 - pct1) * Math.PI
  const largeArc = sweep > Math.PI ? 1 : 0
  // sweep-flag=0 → counterclockwise in SVG → goes upward through top ✓
  return `M ${p1.x} ${p1.y} A ${R} ${R} 0 ${largeArc} 0 ${p2.x} ${p2.y}`
}

// ─── Computed arc paths ───────────────────────────────────────────────────────
const fullTrackPath = computed(() => arcPath(0, 1))

const leftEnd = computed(() => pctToPoint(0))
const rightEnd = computed(() => pctToPoint(1))

const targetRangeArcPath = computed(() => {
  if (!hasTargets.value || targetMin.value == null || targetMax.value == null) return null
  const p1 = valueToPct(targetMin.value)
  const p2 = valueToPct(targetMax.value)
  return arcPath(p1, p2)
})

const valuePct = computed(() => {
  if (!hasValue.value || props.value == null) return null
  return valueToPct(props.value)
})

const valueArcPath = computed(() => {
  if (valuePct.value == null) return null
  return arcPath(0, valuePct.value)
})

const valueDot = computed(() => {
  if (valuePct.value == null) return null
  return pctToPoint(valuePct.value)
})

// ─── Display ─────────────────────────────────────────────────────────────────
const displayValue = computed(() => {
  if (!hasValue.value || props.value == null) return '—'
  return Number(props.value).toFixed(props.decimals)
})

function fmt(v: number | null | undefined, dec?: number): string {
  if (v == null) return '—'
  return Number(v).toFixed(dec ?? props.decimals)
}
</script>
