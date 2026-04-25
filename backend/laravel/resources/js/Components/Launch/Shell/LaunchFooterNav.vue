<template>
  <footer
    class="sticky bottom-0 flex items-center justify-between gap-3 px-5 py-2.5 border-t border-[var(--border-muted)] bg-[var(--bg-surface-strong)] backdrop-blur-sm z-10"
  >
    <div class="flex items-center gap-1.5">
      <Button
        variant="secondary"
        size="sm"
        :disabled="active === 0"
        @click="$emit('back')"
      >
        Назад
      </Button>
      <span class="font-mono text-xs text-[var(--text-dim)]">{{ active + 1 }}/{{ total }}</span>
    </div>

    <div class="flex items-center gap-2">
      <span class="text-xs text-[var(--text-muted)]">
        {{ doneCount }} из {{ total }} завершено
      </span>
      <Button
        v-if="active < total - 1"
        variant="primary"
        size="sm"
        @click="$emit('next')"
      >
        Дальше →
      </Button>
      <Button
        v-else
        variant="success"
        size="sm"
        :disabled="!canLaunch"
        @click="$emit('launch')"
      >
        Запустить цикл
      </Button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import type { StepCompletion } from './types'

const props = defineProps<{
  active: number
  total: number
  completion: readonly StepCompletion[]
  canLaunch?: boolean
}>()

defineEmits<{
  (e: 'back'): void
  (e: 'next'): void
  (e: 'launch'): void
}>()

const doneCount = computed(
  () => props.completion.filter((s) => s === 'done').length,
)
</script>
