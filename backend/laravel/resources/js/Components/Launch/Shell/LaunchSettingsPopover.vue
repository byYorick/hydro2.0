<template>
  <div
    class="absolute right-3 top-12 w-72 z-30 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] shadow-lg p-3 flex flex-col gap-3"
    @click.stop
  >
    <div class="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-dim)]">
      Плотность
    </div>
    <div class="flex gap-1.5">
      <button
        v-for="opt in densityOptions"
        :key="opt.value"
        type="button"
        :class="toggleBtnClass(state.density === opt.value)"
        @click="setDensity(opt.value)"
      >
        {{ opt.label }}
      </button>
    </div>

    <div class="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-dim)] mt-1">
      Степпер
    </div>
    <div class="flex gap-1.5">
      <button
        v-for="opt in stepperOptions"
        :key="opt.value"
        type="button"
        :class="toggleBtnClass(state.stepper === opt.value)"
        @click="setStepper(opt.value)"
      >
        {{ opt.label }}
      </button>
    </div>
    <p
      v-if="state.stepper === 'vertical'"
      class="text-[11px] text-[var(--text-dim)] leading-snug"
    >
      Вертикальный показывается только на экранах ≥1280&nbsp;px;
      на узких автоматически свернётся в горизонтальный.
    </p>

    <label class="flex items-center justify-between gap-2 text-sm mt-1 cursor-pointer">
      <span>Показывать подсказки</span>
      <input
        type="checkbox"
        :checked="state.showHints"
        class="w-4 h-4 accent-brand"
        @change="setShowHints(($event.target as HTMLInputElement).checked)"
      />
    </label>

    <label class="flex items-center justify-between gap-2 text-sm cursor-pointer">
      <span>Тёмная тема</span>
      <input
        type="checkbox"
        :checked="theme.isDark.value"
        class="w-4 h-4 accent-brand"
        @change="theme.toggleTheme()"
      />
    </label>

    <div
      v-if="quickJumpSteps && quickJumpSteps.length > 0"
      class="flex flex-col gap-1 mt-1 pt-2 border-t border-[var(--border-muted)]"
    >
      <div
        class="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-dim)]"
      >
        Быстрый переход
      </div>
      <button
        v-for="(step, i) in quickJumpSteps"
        :key="step.id"
        type="button"
        class="text-left px-2 py-1.5 rounded-md bg-[var(--bg-surface)] hover:bg-[var(--bg-elevated)] border border-[var(--border-muted)] text-xs flex justify-between items-center"
        @click="$emit('jump', i)"
      >
        <span>{{ i + 1 }}. {{ step.label }}</span>
        <span class="font-mono text-[10px] text-[var(--text-dim)]">{{ step.sub }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  useLaunchPreferences,
  type LaunchDensity,
  type LaunchStepper,
} from '@/composables/useLaunchPreferences'
import { useTheme } from '@/composables/useTheme'
import type { LaunchStep } from './types'

defineProps<{
  quickJumpSteps?: readonly LaunchStep[]
}>()

defineEmits<{ (e: 'jump', index: number): void }>()

const { state, setDensity, setStepper, setShowHints } = useLaunchPreferences()
const theme = useTheme()

const densityOptions: Array<{ value: LaunchDensity; label: string }> = [
  { value: 'compact', label: 'Компактная' },
  { value: 'comfortable', label: 'Просторная' },
]

const stepperOptions: Array<{ value: LaunchStepper; label: string }> = [
  { value: 'horizontal', label: 'Горизонтальный' },
  { value: 'vertical', label: 'Вертикальный' },
]

function toggleBtnClass(active: boolean): string {
  return [
    'flex-1 h-8 px-2.5 text-xs font-medium rounded-md border transition',
    active
      ? 'bg-brand text-white border-brand'
      : 'bg-[var(--bg-surface)] text-[var(--text-primary)] border-[var(--border-muted)] hover:border-[var(--border-strong)]',
  ].join(' ')
}
</script>
