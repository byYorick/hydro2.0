<template>
  <div
    class="grid gap-x-3 gap-y-1.5 text-xs"
    style="grid-template-columns: 1fr auto"
  >
    <template
      v-for="(row, i) in rows"
      :key="i"
    >
      <span class="text-[var(--text-dim)]">{{ row[0] }}</span>
      <span class="font-mono text-[var(--text-primary)]">{{ row[1] }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  rows: Array<[string, string | number]>
}>()
</script>
