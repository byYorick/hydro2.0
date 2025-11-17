<template>
  <span :class="classes"><slot /></span>
  </template>
  
  <script setup>
  import { computed } from 'vue'
  
  const props = defineProps({
    variant: { type: String, default: 'neutral' }, // success | warning | danger | info | neutral
  })
  
  const classes = computed(() => {
    const base = 'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium'
    const variants = {
      success: 'bg-emerald-900/40 text-emerald-300 border border-emerald-800',
      warning: 'bg-amber-900/40 text-amber-300 border border-amber-800',
      danger: 'bg-red-900/40 text-red-300 border border-red-800',
      info: 'bg-sky-900/40 text-sky-300 border border-sky-800',
      neutral: 'bg-neutral-800 text-neutral-300 border border-neutral-700',
    }
    return `${base} ${variants[props.variant] ?? variants.neutral}`
  })
  </script>

