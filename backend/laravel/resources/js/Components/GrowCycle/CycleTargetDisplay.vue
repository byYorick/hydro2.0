<template>
  <div class="text-[11px] mb-2 space-y-0.5 text-[color:var(--text-muted)]">
    <div v-if="label">
      {{ label }}
    </div>
    <div
      v-else
      class="text-[color:var(--text-dim)]"
    >
      Таргеты не заданы
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CycleType } from '@/types/Cycle'

interface RecipeTargets {
  min?: number
  max?: number
  temperature?: number
  humidity?: number
  hours_on?: number
  hours_off?: number
  interval_minutes?: number
  duration_seconds?: number
  [key: string]: unknown
}

interface Props {
  type: CycleType
  targets: RecipeTargets | null | undefined
}

const props = defineProps<Props>()

const formatters: Record<CycleType, (t: RecipeTargets) => string | null> = {
  PH_CONTROL: (t) =>
    typeof t.min === 'number' && typeof t.max === 'number'
      ? `pH: ${t.min}–${t.max}`
      : null,
  EC_CONTROL: (t) =>
    typeof t.min === 'number' && typeof t.max === 'number'
      ? `EC: ${t.min}–${t.max}`
      : null,
  CLIMATE: (t) =>
    typeof t.temperature === 'number' && typeof t.humidity === 'number'
      ? `Климат: t=${t.temperature}°C, RH=${t.humidity}%`
      : null,
  LIGHTING: (t) =>
    typeof t.hours_on === 'number'
      ? `Свет: ${t.hours_on}ч / пауза ${typeof t.hours_off === 'number' ? t.hours_off : 24 - t.hours_on}ч`
      : null,
  IRRIGATION: (t) =>
    typeof t.interval_minutes === 'number' && typeof t.duration_seconds === 'number'
      ? `Полив: каждые ${t.interval_minutes} мин, ${t.duration_seconds} с`
      : null,
}

const label = computed((): string | null => {
  if (!props.targets) return null
  return formatters[props.type]?.(props.targets) ?? null
})
</script>
