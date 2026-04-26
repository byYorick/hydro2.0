<template>
  <div
    class="flex items-center gap-2 py-1.5 border-b border-[var(--border-muted)] last:border-b-0"
  >
    <span :class="['inline-flex items-center justify-center w-4 shrink-0', iconColorClass]">
      <span class="font-mono text-[13px] leading-none">{{ icon }}</span>
    </span>
    <span class="flex-1 text-sm text-[var(--text-primary)]">{{ label }}</span>
    <span
      v-if="note"
      class="font-mono text-[11px] text-[var(--text-dim)]"
    >{{ note }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type ReadinessStatus = 'ok' | 'warn' | 'err'

const props = defineProps<{
  label: string
  status: ReadinessStatus
  note?: string | null
}>()

const icon = computed(() => {
  if (props.status === 'ok') return '✓'
  if (props.status === 'warn') return '!'
  return '×'
})

const iconColorClass = computed(() => {
  if (props.status === 'ok') return 'text-growth'
  if (props.status === 'warn') return 'text-warn'
  return 'text-alert'
})
</script>
