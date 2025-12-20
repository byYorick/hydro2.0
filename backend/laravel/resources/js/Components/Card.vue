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
  const base = 'surface-card relative overflow-hidden p-5 text-[color:var(--text-primary)]'
  const tone = props.variant === 'elevated' ? 'surface-strong shadow-[0_25px_60px_rgba(0,0,0,0.3)]' : ''
  return [base, tone, attrs.class].filter(Boolean).join(' ')
})
</script>
