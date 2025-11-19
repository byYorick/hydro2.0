<template>
  <button :class="classes" v-bind="$attrs"><slot /></button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type ButtonVariant = 'primary' | 'secondary' | 'outline'
type ButtonSize = 'sm' | 'md'

interface Props {
  variant?: ButtonVariant
  size?: ButtonSize
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md'
})

const classes = computed(() => {
  const base = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-600/50'
  const variants: Record<ButtonVariant, string> = {
    primary: 'bg-sky-600 hover:bg-sky-500 text-white',
    secondary: 'bg-neutral-800 hover:bg-neutral-700 text-neutral-100',
    outline: 'border border-neutral-700 hover:border-neutral-600 text-neutral-100',
  }
  const sizes: Record<ButtonSize, string> = {
    sm: 'h-8 px-3 text-xs',
    md: 'h-9 px-4 text-sm',
  }
  return `${base} ${variants[props.variant] ?? variants.primary} ${sizes[props.size] ?? sizes.md}`
})
</script>

