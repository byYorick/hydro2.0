<template>
  <button :class="classes" v-bind="$attrs">
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost'
type ButtonSize = 'sm' | 'md'

interface Props {
  variant?: ButtonVariant
  size?: ButtonSize
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md'
})

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'inline-flex items-center justify-center rounded-xl font-semibold transition duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-emerald-300/60 focus-visible:ring-offset-neutral-900 shadow-sm tracking-tight'
  const variants: Record<ButtonVariant, string> = {
    primary: 'bg-gradient-to-r from-emerald-300/90 via-cyan-300/90 to-amber-300/90 text-neutral-900 hover:shadow-[0_15px_35px_rgba(48,240,201,0.25)]',
    secondary: 'bg-neutral-900/80 text-slate-100 border border-slate-700/70 hover:border-slate-500/80 hover:shadow-[0_10px_30px_rgba(0,0,0,0.45)] backdrop-blur-md',
    outline: 'border border-slate-600/70 text-slate-100 hover:border-emerald-300/70 hover:text-white bg-neutral-900/40',
    ghost: 'bg-transparent text-slate-200 hover:text-white hover:bg-white/5 border border-transparent',
  }
  const sizes: Record<ButtonSize, string> = {
    sm: 'h-9 px-3 text-xs',
    md: 'h-11 px-5 text-sm',
  }
  return [base, variants[props.variant] ?? variants.primary, sizes[props.size] ?? sizes.md, attrs.class]
    .filter(Boolean)
    .join(' ')
})
</script>
