<template>
  <span :class="classes" v-bind="$attrs"><slot /></span>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
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
  const base = 'inline-flex items-center justify-center rounded-full font-semibold tracking-wide px-3 py-1 bg-opacity-70'
  const variants: Record<BadgeVariant, string> = {
    success: 'bg-emerald-900 text-emerald-300 border border-emerald-800',
    warning: 'bg-amber-900 text-amber-300 border border-amber-800',
    danger: 'bg-red-900 text-red-300 border border-red-800',
    info: 'bg-sky-900 text-sky-300 border border-sky-800',
    neutral: 'bg-neutral-800 text-neutral-300 border border-neutral-700',
  }
  const sizes: Record<BadgeSize, string> = {
    xs: 'text-[0.65rem]',
    sm: 'text-[0.75rem]',
  }
  return [base, variants[props.variant] ?? variants.neutral, sizes[props.size] ?? sizes.xs, attrs.class]
    .filter(Boolean)
    .join(' ')
})
</script>
