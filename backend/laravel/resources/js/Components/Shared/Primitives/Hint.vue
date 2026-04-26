<template>
  <div
    v-if="show"
    class="flex gap-2 px-3 py-2 rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--bg-main)]/40 text-xs text-[var(--text-muted)] leading-relaxed"
  >
    <span class="text-brand shrink-0 mt-0.5">
      <svg
        width="14"
        height="14"
        viewBox="0 0 14 14"
        fill="none"
        aria-hidden="true"
      >
        <circle
          cx="7"
          cy="7"
          r="5.5"
          stroke="currentColor"
          stroke-width="1.2"
        />
        <path
          d="M7 5v3"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
        />
        <circle
          cx="7"
          cy="9.6"
          r=".6"
          fill="currentColor"
        />
      </svg>
    </span>
    <div class="flex-1 min-w-0">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ show?: boolean }>(), { show: true })
</script>
