<template>
  <div class="flex items-baseline justify-between gap-3">
    <div>
      <div
        class="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-dim)]"
      >
        Шаг
        <span class="font-mono">{{ index + 1 }}/{{ total }}</span>
      </div>
      <h1 class="mt-0.5 text-[22px] font-semibold tracking-tight">
        {{ step.label }}
        <span class="font-normal text-[15px] text-[var(--text-dim)]">· {{ step.sub }}</span>
      </h1>
    </div>
    <div
      v-if="$slots.right"
      class="flex items-center gap-1.5"
    >
      <slot name="right"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LaunchStep } from './types'

defineProps<{
  step: LaunchStep
  index: number
  total: number
}>()
</script>
