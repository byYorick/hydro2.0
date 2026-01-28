<template>
  <div :class="classes">
    <div
      v-if="iconValue"
      class="text-3xl"
      :class="iconClass"
    >
      {{ iconValue }}
    </div>
    <div class="text-sm font-semibold text-[color:var(--text-primary)]">
      {{ title }}
    </div>
    <p
      v-if="description"
      class="text-xs text-[color:var(--text-muted)] max-w-md"
    >
      {{ description }}
    </p>
    <div
      v-if="$slots.action"
      class="mt-3"
    >
      <slot name="action"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

type EmptyStateVariant = 'empty' | 'error' | 'loading'

interface Props {
  title: string
  description?: string
  icon?: string
  variant?: EmptyStateVariant
  containerClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  icon: undefined,
  variant: 'empty',
  containerClass: '',
})

const attrs = useAttrs()

const defaultIcons: Record<EmptyStateVariant, string> = {
  empty: '',
  error: '!',
  loading: '',
}

const iconValue = computed(() => {
  if (props.icon !== undefined) {
    return props.icon
  }
  return defaultIcons[props.variant]
})

const iconClass = computed(() => {
  switch (props.variant) {
    case 'error':
      return 'text-[color:var(--accent-red)]'
    case 'loading':
      return 'text-[color:var(--accent-cyan)]'
    default:
      return 'text-[color:var(--text-dim)]'
  }
})

const classes = computed(() => {
  const base = 'flex flex-col items-center justify-center gap-2 text-center py-6'
  return [base, props.containerClass, attrs.class].filter(Boolean).join(' ')
})
</script>
