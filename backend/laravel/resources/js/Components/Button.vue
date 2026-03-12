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
  const base = 'inline-flex items-center justify-center rounded-xl font-semibold transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-sky-500/50 shadow-sm'
  const variants: Record<ButtonVariant, string> = {
    primary: 'bg-gradient-to-r from-sky-600 to-sky-500 hover:from-sky-500 hover:to-sky-400 text-white shadow-[0_12px_24px_rgba(14,165,233,0.4)]',
    secondary: 'bg-neutral-800 hover:bg-neutral-700 text-neutral-100 border border-transparent',
    outline: 'border border-neutral-700 hover:border-neutral-600 text-neutral-100 bg-transparent',
    ghost: 'bg-transparent text-neutral-100 hover:text-white hover:bg-neutral-900 border border-transparent',
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
