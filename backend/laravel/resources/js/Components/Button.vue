<template>
  <button :class="classes" v-bind="$attrs"><slot /></button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: { type: String, default: 'primary' }, // primary | secondary | outline
  size: { type: String, default: 'md' }, // sm | md
})

const classes = computed(() => {
  const base = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-600/50'
  const variants = {
    primary: 'bg-sky-600 hover:bg-sky-500 text-white',
    secondary: 'bg-neutral-800 hover:bg-neutral-700 text-neutral-100',
    outline: 'border border-neutral-700 hover:border-neutral-600 text-neutral-100',
  }
  const sizes = {
    sm: 'h-8 px-3 text-xs',
    md: 'h-9 px-4 text-sm',
  }
  return `${base} ${variants[props.variant] ?? variants.primary} ${sizes[props.size] ?? sizes.md}`
})
</script>

