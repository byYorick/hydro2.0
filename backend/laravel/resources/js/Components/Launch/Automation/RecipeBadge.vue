<template>
  <div
    class="flex items-center gap-2 px-3 py-2 rounded-md border border-brand bg-brand-soft text-xs text-[var(--text-primary)] flex-wrap"
  >
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      class="text-brand shrink-0"
      aria-hidden="true"
    >
      <rect
        x="3"
        y="6.5"
        width="8"
        height="5.5"
        rx="0.8"
        stroke="currentColor"
        stroke-width="1.2"
      />
      <path
        d="M5 6.5V4.5a2 2 0 014 0v2"
        stroke="currentColor"
        stroke-width="1.2"
        stroke-linecap="round"
      />
    </svg>
    <span>
      Из рецепта
      <strong
        v-if="recipeName"
        class="font-mono"
      >{{ recipeName }}</strong>
      <span
        v-if="revisionLabel"
        class="font-mono text-brand-ink"
      >· {{ revisionLabel }}</span>:
    </span>
    <span
      v-if="systemType"
      class="font-mono"
    >system = <b>{{ systemType }}</b></span>
    <span
      v-if="systemType && (targetPh != null || targetEc != null)"
      class="text-[var(--text-dim)]"
    >·</span>
    <span
      v-if="targetPh != null"
      class="font-mono"
    >targetPh = <b>{{ targetPh }}</b></span>
    <span
      v-if="targetPh != null && targetEc != null"
      class="text-[var(--text-dim)]"
    >·</span>
    <span
      v-if="targetEc != null"
      class="font-mono"
    >targetEc = <b>{{ targetEc }}</b></span>
    <span class="flex-1"></span>
    <span class="text-[11px] text-[var(--text-dim)]">
      Изменения — только в шаге «Рецепт».
    </span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  recipeName?: string | null
  revisionLabel?: string | null
  systemType?: string | null
  targetPh?: number | null
  targetEc?: number | null
}>()
</script>
