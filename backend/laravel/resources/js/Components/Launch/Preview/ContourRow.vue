<template>
  <div
    class="flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]"
  >
    <span class="text-brand shrink-0 flex items-center w-4 h-4">
      <slot name="icon"></slot>
    </span>
    <span class="text-sm w-16 shrink-0">{{ label }}</span>
    <span
      class="font-mono text-xs text-[var(--text-muted)] flex-1 min-w-0 truncate"
    >{{ node || 'не задано' }}</span>
    <Chip :tone="tone">
      <template #icon>
        <span
          class="inline-block w-1.5 h-1.5 rounded-full"
          :class="dotClass"
        ></span>
      </template>
      {{ statusLabel }}
    </Chip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'

const props = withDefaults(
  defineProps<{
    label: string
    node?: string | null
    bound?: boolean
  }>(),
  { node: null, bound: false },
)

const tone = computed<ChipTone>(() => (props.bound ? 'growth' : 'warn'))

const dotClass = computed(() =>
  props.bound ? 'bg-growth' : 'bg-warn',
)

const statusLabel = computed(() => (props.bound ? 'привязано' : 'не задано'))
</script>
