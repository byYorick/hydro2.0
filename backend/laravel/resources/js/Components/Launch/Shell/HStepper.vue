<template>
  <div
    class="flex items-center gap-0 px-5 py-3 border-b border-[var(--border-muted)] bg-[var(--bg-surface)] overflow-x-auto"
  >
    <template
      v-for="(step, i) in steps"
      :key="step.id"
    >
      <button
        type="button"
        :aria-current="i === active ? 'step' : undefined"
        :class="[
          'flex items-center gap-2.5 px-2.5 py-1.5 bg-transparent border-0 rounded-md whitespace-nowrap text-left',
          completion[i] === 'todo' && i !== active
            ? 'text-[var(--text-dim)]'
            : 'text-[var(--text-primary)]',
        ]"
        @click="$emit('select', i)"
      >
        <span
          :class="[
            'w-5 h-5 rounded-full inline-flex items-center justify-center text-[11px] font-semibold border',
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
        <span class="flex flex-col leading-tight">
          <span class="text-sm font-medium">{{ step.label }}</span>
          <span class="text-[11px] text-[var(--text-dim)]">{{ step.sub }}</span>
        </span>
      </button>
      <span
        v-if="i < steps.length - 1"
        :class="[
          'flex-auto min-w-[24px] h-px mx-0.5',
          completion[i] === 'done' ? 'bg-brand' : 'bg-[var(--border-muted)]',
        ]"
        aria-hidden="true"
      ></span>
    </template>
  </div>
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
