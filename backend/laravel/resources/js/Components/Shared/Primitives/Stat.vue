<template>
  <div>
    <div
      class="flex items-center gap-1 text-[11px] uppercase tracking-wider text-[var(--text-dim)] font-medium"
    >
      <span
        v-if="$slots.icon"
        class="flex items-center"
      >
        <slot name="icon"></slot>
      </span>
      <span>{{ label }}</span>
    </div>
    <div
      :class="[
        'text-sm font-medium leading-tight',
        toneClass,
        mono ? 'font-mono' : 'font-sans',
      ]"
    >
      {{ value }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type StatTone = 'default' | 'brand' | 'growth'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number | null | undefined
    mono?: boolean
    tone?: StatTone
  }>(),
  { tone: 'default' },
)

const toneClass = computed(
  () =>
    ({
      default: 'text-[var(--text-primary)]',
      brand: 'text-brand-ink',
      growth: 'text-growth',
    })[props.tone],
)
</script>
