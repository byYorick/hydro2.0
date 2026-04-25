<template>
  <div
    class="flex flex-col gap-0.5 pb-2.5 mb-3.5 border-b border-[var(--border-muted)]"
  >
    <div class="font-mono text-[11px] text-[var(--text-dim)]">
      / зона / автоматика / {{ sub }}
    </div>
    <div class="text-[15px] font-semibold text-[var(--text-primary)]">
      {{ title }}
    </div>
    <div class="text-xs text-[var(--text-muted)]">
      {{ description }}
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  sub: string
  title: string
  description: string
}>()
</script>
