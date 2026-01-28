<template>
  <section
    :class="classes"
    v-bind="attrs"
  >
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div class="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2 flex-1">
        <slot></slot>
      </div>
      <div
        v-if="$slots.actions"
        class="flex flex-wrap items-center gap-2"
      >
        <slot name="actions"></slot>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'surface-card border border-[color:var(--border-muted)] rounded-2xl p-4'
  return [base, attrs.class].filter(Boolean).join(' ')
})
</script>
