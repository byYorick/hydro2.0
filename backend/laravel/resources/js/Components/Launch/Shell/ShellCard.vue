<template>
  <section
    class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-hidden"
  >
    <header
      v-if="title || $slots.title || $slots.actions"
      class="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-[var(--border-muted)]"
    >
      <div class="text-sm font-semibold text-[var(--text-primary)]">
        <slot name="title">
          {{ title }}
        </slot>
      </div>
      <div
        v-if="$slots.actions"
        class="flex items-center gap-1.5"
      >
        <slot name="actions"></slot>
      </div>
    </header>
    <div :class="pad ? 'p-3.5' : ''">
      <slot></slot>
    </div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    pad?: boolean
  }>(),
  { pad: true },
)
</script>
