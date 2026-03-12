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
  const base = 'surface-card relative overflow-hidden bg-opacity-95 p-4 backdrop-blur-md'
  const tone = props.variant === 'elevated' ? 'surface-strong border border-neutral-700/60' : 'border border-neutral-800'
  return [base, tone, attrs.class].filter(Boolean).join(' ')
})
</script>
