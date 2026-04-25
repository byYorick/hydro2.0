<template>
  <span
    :class="[
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium leading-tight',
      toneClass,
    ]"
  >
    <span
      v-if="$slots.icon"
      class="flex items-center"
    >
      <slot name="icon"></slot>
    </span>
    <slot></slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type ChipTone = 'neutral' | 'brand' | 'growth' | 'warn' | 'alert'

const props = withDefaults(defineProps<{ tone?: ChipTone }>(), { tone: 'neutral' })

const toneClass = computed(
  () =>
    ({
      neutral:
        'bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-muted)]',
      brand: 'bg-brand-soft text-brand-ink border-brand-soft',
      growth: 'bg-growth-soft text-growth border-growth-soft',
      warn: 'bg-warn-soft text-warn border-warn-soft',
      alert: 'bg-alert-soft text-alert border-alert-soft',
    })[props.tone],
)
</script>
