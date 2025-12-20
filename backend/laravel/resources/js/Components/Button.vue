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
  const base = 'btn shadow-sm'
  const variants: Record<ButtonVariant, string> = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    outline: 'btn-outline',
    ghost: 'btn-ghost',
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
