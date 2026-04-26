<template>
  <label class="flex flex-col gap-1 min-w-0">
    <span class="flex items-center justify-between gap-2">
      <span class="text-xs font-medium text-[var(--text-muted)]">
        {{ label }}<span
          v-if="required"
          class="text-alert"
        > *</span>
      </span>
      <span
        v-if="$slots.right"
        class="flex items-center gap-1.5"
      >
        <slot name="right"></slot>
      </span>
    </span>
    <slot></slot>
    <span
      v-if="hint && !error"
      class="text-[11px] text-[var(--text-dim)]"
    >{{ hint }}</span>
    <span
      v-if="error"
      class="text-[11px] text-alert"
    >{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  hint?: string
  error?: string
  required?: boolean
}>()
</script>
