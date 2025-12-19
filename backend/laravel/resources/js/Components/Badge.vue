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
  const base = 'inline-flex items-center justify-center rounded-full font-semibold tracking-[0.08em] px-3 py-1 bg-opacity-80 uppercase'
  const variants: Record<BadgeVariant, string> = {
    success: 'bg-emerald-900/70 text-emerald-200 border border-emerald-500/60 shadow-[0_0_0_1px_rgba(16,185,129,0.35)]',
    warning: 'bg-amber-900/70 text-amber-200 border border-amber-500/60 shadow-[0_0_0_1px_rgba(245,159,69,0.4)]',
    danger: 'bg-rose-900/70 text-rose-200 border border-rose-500/60 shadow-[0_0_0_1px_rgba(255,77,103,0.4)]',
    info: 'bg-cyan-900/70 text-cyan-200 border border-cyan-500/60 shadow-[0_0_0_1px_rgba(48,240,201,0.4)]',
    neutral: 'bg-slate-900/70 text-slate-200 border border-slate-600/70',
  }
  const sizes: Record<BadgeSize, string> = {
    xs: 'text-[0.62rem]',
    sm: 'text-[0.72rem]',
  }
  return [base, variants[props.variant] ?? variants.neutral, sizes[props.size] ?? sizes.xs, attrs.class]
    .filter(Boolean)
    .join(' ')
})
</script>
