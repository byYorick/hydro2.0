<template>
  <div class="relative inline-flex items-center justify-center">
    <svg
      :width="size"
      :height="size"
      class="transform -rotate-90"
    >
      <!-- Фоновый круг -->
      <circle
        :cx="center"
        :cy="center"
        :r="radius"
        :stroke-width="strokeWidth"
        stroke="currentColor"
        class="text-[color:var(--border-muted)]"
        fill="none"
      />
      
      <!-- Прогресс -->
      <circle
        :cx="center"
        :cy="center"
        :r="radius"
        :stroke-width="strokeWidth"
        stroke="currentColor"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
        class="transition-all duration-500 ease-out"
        :class="progressColorClass"
        fill="none"
        stroke-linecap="round"
      />
    </svg>
    
    <!-- Текст внутри -->
    <div class="absolute inset-0 flex flex-col items-center justify-center">
      <span class="text-2xl font-bold" :class="textColorClass">
        {{ Math.round(progress) }}%
      </span>
      <span v-if="label" class="text-xs text-[color:var(--text-muted)] mt-0.5">
        {{ label }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  progress: number // 0-100
  size?: number
  strokeWidth?: number
  label?: string
  variant?: 'primary' | 'success' | 'warning' | 'danger'
}

const props = withDefaults(defineProps<Props>(), {
  progress: 0,
  size: 120,
  strokeWidth: 8,
  label: '',
  variant: 'primary',
})

const center = computed(() => props.size / 2)
const radius = computed(() => (props.size - props.strokeWidth) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)

const offset = computed(() => {
  const progressValue = Math.max(0, Math.min(100, props.progress))
  return circumference.value - (progressValue / 100) * circumference.value
})

const progressColorClass = computed(() => {
  switch (props.variant) {
    case 'success':
      return 'text-[color:var(--accent-green)]'
    case 'warning':
      return 'text-[color:var(--accent-amber)]'
    case 'danger':
      return 'text-[color:var(--accent-red)]'
    default:
      return 'text-[color:var(--accent-cyan)]'
  }
})

const textColorClass = computed(() => {
  switch (props.variant) {
    case 'success':
      return 'text-[color:var(--accent-green)]'
    case 'warning':
      return 'text-[color:var(--accent-amber)]'
    case 'danger':
      return 'text-[color:var(--accent-red)]'
    default:
      return 'text-[color:var(--accent-cyan)]'
  }
})
</script>
