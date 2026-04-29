<template>
  <div class="flex flex-wrap items-center gap-2">
    <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Диапазон</span>
    <button
      v-for="range in telemetryRanges"
      :key="range"
      type="button"
      class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
      :class="range === modelValue
        ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
        : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
      @click="emit('update:modelValue', range)"
    >
      {{ range }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { telemetryRanges, type TelemetryRange } from '@/types'

interface Props {
  modelValue: TelemetryRange
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: TelemetryRange): void
}>()
</script>
