<template>
  <div
    v-if="phases.length === 0"
    class="px-3 py-3 text-xs text-[var(--text-dim)] text-center"
  >
    Фазы появятся после выбора рецепта
  </div>
  <div v-else>
    <div class="flex h-7 border-y border-[var(--border-muted)]">
      <div
        v-for="(p, i) in phases"
        :key="i"
        :style="{ flex: phaseFlex(p) }"
        :class="[
          'flex items-center justify-between gap-1.5 px-2 text-[11px] text-[var(--text-muted)] border-r border-[var(--border-muted)] last:border-r-0 overflow-hidden whitespace-nowrap',
          toneClass(i),
        ]"
      >
        <span class="truncate">{{ p.name ?? `Фаза ${i + 1}` }}</span>
        <span
          v-if="p.days"
          class="font-mono text-[10px] shrink-0"
        >{{ p.days }}д</span>
      </div>
    </div>
    <div
      v-if="expanded"
      class="grid"
      :style="`grid-template-columns: repeat(${phases.length}, 1fr)`"
    >
      <div
        v-for="(p, i) in phases"
        :key="i"
        class="px-2.5 py-1.5 border-r border-[var(--border-muted)] last:border-r-0 font-mono text-[11px] text-[var(--text-muted)]"
      >
        pH {{ p.ph ?? '—' }} · EC {{ p.ec ?? '—' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface PhasePreview {
  id?: number
  name?: string | null
  days?: number | null
  ph?: number | null
  ec?: number | null
}

const props = withDefaults(
  defineProps<{
    phases?: readonly PhasePreview[]
    expanded?: boolean
  }>(),
  { phases: () => [], expanded: false },
)

const total = computed(
  () => props.phases.reduce((s, p) => s + (p.days ?? 1), 0) || 1,
)

function phaseFlex(p: PhasePreview): number {
  return (p.days ?? 1) / total.value
}

const PHASE_TONES = [
  'bg-growth-soft',
  'bg-brand-soft',
  'bg-warn-soft',
  'bg-[var(--bg-elevated)]',
] as const

function toneClass(i: number): string {
  return PHASE_TONES[i % PHASE_TONES.length]
}
</script>
