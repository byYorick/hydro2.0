<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/50 p-3 space-y-3">
    <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
      Показатели
    </h4>

    <dl class="grid grid-cols-2 gap-2">
      <div class="metric-tile">
        <dt>Чистая вода</dt>
        <dd>{{ cleanTankLevel }}%</dd>
      </div>
      <div class="metric-tile">
        <dt>Раствор</dt>
        <dd>{{ nutrientTankLevel }}%</dd>
      </div>
      <div
        v-if="bufferTankLevel > 0"
        class="metric-tile"
      >
        <dt>Буфер</dt>
        <dd>{{ bufferTankLevel }}%</dd>
      </div>
      <div class="metric-tile">
        <dt>pH</dt>
        <dd>{{ formatMetric(ph) }}</dd>
      </div>
      <div class="metric-tile">
        <dt>EC</dt>
        <dd>{{ formatMetric(ec, ' mS/cm') }}</dd>
      </div>
    </dl>

    <div
      v-if="activeChips.length > 0"
      class="flex flex-wrap gap-1.5"
    >
      <span
        v-for="chip in activeChips"
        :key="chip.key"
        class="rounded-full border px-2 py-0.5 text-[10px] font-medium"
        :class="chip.active ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : 'border-[color:var(--border-muted)]/50 text-[color:var(--text-dim)]'"
      >
        {{ chip.label }}
      </span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AutomationState } from '@/types/Automation'

interface Props {
  automationState: AutomationState | null
  cleanTankLevel: number
  nutrientTankLevel: number
  bufferTankLevel: number
  isPumpInActive: boolean
  isCirculationActive: boolean
  isPhCorrectionActive: boolean
  isEcCorrectionActive: boolean
  isIrrigationActive: boolean
}

const props = defineProps<Props>()

const ph = computed(() => props.automationState?.current_levels.ph ?? null)
const ec = computed(() => props.automationState?.current_levels.ec ?? null)

const activeChips = computed(() => [
  { key: 'pump', label: 'Насос', active: props.isPumpInActive },
  { key: 'circ', label: 'Рециркуляция', active: props.isCirculationActive },
  { key: 'ph', label: 'Коррекция pH', active: props.isPhCorrectionActive },
  { key: 'ec', label: 'Коррекция EC', active: props.isEcCorrectionActive },
  { key: 'irr', label: 'Полив', active: props.isIrrigationActive },
].filter((chip) => chip.active))

function formatMetric(value: number | null, suffix = ''): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '—'
  }
  return `${Number(value).toFixed(2)}${suffix}`
}
</script>

<style scoped>
.metric-tile {
  border-radius: 0.65rem;
  border: 1px solid rgb(100 116 139 / 0.25);
  background: rgb(15 23 42 / 0.2);
  padding: 0.5rem 0.65rem;
}

.metric-tile dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

.metric-tile dd {
  margin-top: 0.15rem;
  font-size: 0.95rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
