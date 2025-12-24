<template>
  <div :class="classes" v-bind="$attrs">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

interface Props {
  variant?: 'default' | 'elevated'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default'
})

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'glass-panel relative overflow-hidden p-5 backdrop-blur-lg text-slate-100'
  const tone = props.variant === 'elevated' ? 'border border-emerald-400/40 shadow-[0_25px_60px_rgba(0,0,0,0.45)]' : 'border border-slate-700/60'
  return [base, tone, attrs.class].filter(Boolean).join(' ')
})
</script>
