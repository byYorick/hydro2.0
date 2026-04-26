<template>
  <svg
    :viewBox="`0 0 ${W} ${H}`"
    width="100%"
    aria-label="PID dead/close/far zones"
  >
    <rect
      :x="cx - bandWidth(far)"
      :y="20"
      :width="bandWidth(far) * 2"
      :height="H - 40"
      class="fill-alert-soft"
      opacity="0.6"
    />
    <rect
      :x="cx - bandWidth(close)"
      :y="20"
      :width="bandWidth(close) * 2"
      :height="H - 40"
      class="fill-warn-soft"
      opacity="0.7"
    />
    <rect
      :x="cx - bandWidth(dead)"
      :y="20"
      :width="bandWidth(dead) * 2"
      :height="H - 40"
      class="fill-growth-soft"
      opacity="0.85"
    />
    <line
      :x1="cx"
      :x2="cx"
      :y1="10"
      :y2="H - 10"
      class="stroke-brand"
      stroke-width="1.4"
    />
    <text
      :x="cx + 4"
      :y="18"
      class="fill-[var(--text-muted)] font-mono"
      font-size="10"
    >target {{ target }}</text>
    <text
      x="6"
      :y="H - 4"
      class="fill-[var(--text-dim)] font-mono"
      font-size="10"
    >{{ axisLabel }} −{{ far }}</text>
    <text
      :x="W - 36"
      :y="H - 4"
      class="fill-[var(--text-dim)] font-mono"
      font-size="10"
    >+{{ far }}</text>
  </svg>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    target: number
    dead: number
    close: number
    far: number
    /** "pH" или "EC" — подпись оси. */
    axisLabel?: string
  }>(),
  { axisLabel: 'pH' },
)

const W = 300
const H = 140
const cx = W / 2

function bandWidth(value: number): number {
  if (props.far === 0) return 0
  return Math.min(W * 0.45, (W * 0.45 * value) / props.far)
}
</script>
