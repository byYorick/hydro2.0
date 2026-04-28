<template>
  <aside
    class="w-60 min-w-[240px] border-r border-[var(--border-muted)] bg-[var(--bg-surface-strong)] p-3 flex flex-col gap-2.5"
  >
    <div
      class="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-dim)] px-1.5"
    >
      Этапы запуска
    </div>
    <ol class="list-none m-0 p-0 flex flex-col gap-0.5">
      <li
        v-for="(step, i) in steps"
        :key="step.id"
      >
        <button
          type="button"
          :aria-current="i === active ? 'step' : undefined"
          :class="[
            'flex items-center gap-2.5 w-full px-2 py-2 border rounded-lg text-left transition-colors',
            i === active
              ? 'border-brand-soft bg-brand-soft text-brand-ink'
              : 'border-transparent bg-transparent hover:bg-[var(--bg-elevated)]',
            completion[i] === 'todo' && i !== active
              ? 'text-[var(--text-dim)]'
              : i === active
                ? 'text-brand-ink'
                : 'text-[var(--text-primary)]',
          ]"
          @click="$emit('select', i)"
        >
          <span
            :class="[
              'w-5 h-5 rounded-full inline-flex items-center justify-center text-[11px] font-semibold border shrink-0',
              bulletClass(i),
            ]"
            aria-hidden="true"
          >
            <template v-if="resolveState(i) === 'done'">✓</template>
            <template v-else-if="resolveState(i) === 'warn'">!</template>
            <span
              v-else
              class="font-mono"
            >{{ i + 1 }}</span>
          </span>
          <span class="flex flex-col leading-tight flex-1 min-w-0">
            <span class="text-sm font-medium">{{ step.label }}</span>
            <span class="text-[11px] text-[var(--text-dim)]">{{ step.sub }}</span>
          </span>
        </button>
      </li>
    </ol>
  </aside>
</template>

<script setup lang="ts">
import type { LaunchStep, StepCompletion } from './types'

const props = defineProps<{
  steps: readonly LaunchStep[]
  active: number
  completion: readonly StepCompletion[]
}>()

defineEmits<{ (e: 'select', index: number): void }>()

function resolveState(i: number): StepCompletion {
  if (i === props.active) return 'current'
  return props.completion[i]
}

function bulletClass(i: number): string {
  const state = resolveState(i)
  if (state === 'done') return 'bg-brand text-white border-brand'
  if (state === 'current')
    return 'border-brand text-brand bg-[var(--bg-surface)] ring-2 ring-brand-soft'
  if (state === 'warn') return 'bg-warn text-white border-warn'
  return 'bg-[var(--bg-surface)] text-[var(--text-muted)] border-[var(--border-strong)]'
}
</script>
