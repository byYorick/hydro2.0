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
  </div>
</template>

<script setup lang="ts">
import {
  useLaunchPreferences,
  type LaunchDensity,
  type LaunchStepper,
} from '@/composables/useLaunchPreferences'

const { state, setDensity, setStepper, setShowHints } = useLaunchPreferences()

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
