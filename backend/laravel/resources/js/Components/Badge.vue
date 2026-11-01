<template>
  <span
    :class="classes"
    v-bind="$attrs"
  ><slot></slot></span>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { badgeVariantClass } from '@/theme/statusTones'

export type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'secondary' | 'ok' | 'critical' | 'offline'
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
  const sizes: Record<BadgeSize, string> = {
    xs: 'badge--xs',
    sm: 'badge--sm',
  }
  return [base, badgeVariantClass(props.variant), sizes[props.size] ?? sizes.xs, attrs.class]
    .filter(Boolean)
    .join(' ')
})
</script>
