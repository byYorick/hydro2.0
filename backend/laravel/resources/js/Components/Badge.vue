<template>
  <span :class="classes" v-bind="$attrs"><slot /></span>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'secondary'
type BadgeSize = 'xs' | 'sm'

interface Props {
  variant?: BadgeVariant
  size?: BadgeSize
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'neutral',
  size: 'xs',
})

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'badge'
  const variants: Record<BadgeVariant, string> = {
    success: 'badge--success',
    warning: 'badge--warning',
    danger: 'badge--danger',
    info: 'badge--info',
    neutral: 'badge--neutral',
    secondary: 'badge--secondary',
  }
  const sizes: Record<BadgeSize, string> = {
    xs: 'badge--xs',
    sm: 'badge--sm',
  }
  return [base, variants[props.variant] ?? variants.neutral, sizes[props.size] ?? sizes.xs, attrs.class]
    .filter(Boolean)
    .join(' ')
})
</script>
