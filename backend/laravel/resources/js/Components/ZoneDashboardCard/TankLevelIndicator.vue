<template>
  <div class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-2 py-1.5">
    <div class="flex items-baseline justify-between gap-1">
      <span class="text-[9px] uppercase tracking-wider text-[color:var(--text-muted)] truncate">
        {{ label }}
      </span>
      <span
        class="text-[11px] tabular-nums font-medium"
        :class="valueColorClass"
      >
        {{ displayValue }}
      </span>
    </div>
    <div class="mt-1 h-1 w-full rounded-full bg-[color:var(--border-muted)] overflow-hidden">
      <div
        v-if="!offline && percent !== null"
        class="h-full rounded-full transition-all duration-500"
        :class="barColorClass"
        :style="{ width: `${clampedPercent}%` }"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  percent: number | null
  offline?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  offline: false,
})

const clampedPercent = computed(() => {
  if (props.percent === null) return 0
  return Math.max(0, Math.min(100, props.percent))
})

const displayValue = computed(() => {
  if (props.offline) return 'offline'
  if (props.percent === null) return '—'
  return `${Math.round(props.percent)}%`
})

const valueColorClass = computed(() => {
  if (props.offline) return 'text-[color:var(--accent-red)]'
  if (props.percent === null) return 'text-[color:var(--text-dim)]'
  if (props.percent < 15) return 'text-[color:var(--accent-red)]'
  if (props.percent < 30) return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--text-primary)]'
})

const barColorClass = computed(() => {
  if (props.percent === null) return 'bg-[color:var(--text-dim)]'
  if (props.percent < 15) return 'bg-[color:var(--accent-red)]'
  if (props.percent < 30) return 'bg-[color:var(--accent-amber)]'
  return 'bg-[color:var(--accent-cyan)]'
})
</script>
