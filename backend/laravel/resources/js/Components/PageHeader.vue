<template>
  <section
    :class="classes"
    v-bind="attrs"
  >
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div class="min-w-0">
        <p
          v-if="eyebrow"
          class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]"
        >
          {{ eyebrow }}
        </p>
        <h1 class="text-2xl font-semibold tracking-tight mt-1 text-[color:var(--text-primary)]">
          {{ title }}
        </h1>
        <p
          v-if="subtitle"
          class="text-sm text-[color:var(--text-dim)] mt-1"
        >
          {{ subtitle }}
        </p>
      </div>
      <div
        v-if="$slots.actions"
        class="flex flex-wrap gap-2 justify-end"
      >
        <slot name="actions"></slot>
      </div>
    </div>
    <div
      v-if="$slots.default"
      class="mt-4"
    >
      <slot></slot>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  title: string
  subtitle?: string
  eyebrow?: string
}

defineProps<Props>()

const attrs = useAttrs()

const classes = computed(() => {
  const base = 'ui-hero p-5'
  return [base, attrs.class].filter(Boolean).join(' ')
})
</script>
