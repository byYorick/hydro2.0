<template>
  <div
    :class="classes"
    v-bind="$attrs"
  >
    <slot></slot>
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
  const tone = props.variant === 'elevated' ? 'surface-strong surface-card--elevated' : ''
  return [base, tone, attrs.class].filter(Boolean).join(' ')
})
</script>
