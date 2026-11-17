<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/50 p-3 space-y-3">
    <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
      Показатели
    </h4>

    <dl class="grid grid-cols-2 gap-2">
      <div class="metric-tile">
        <dt>Уровень чистой воды</dt>
        <dd>{{ levelLabel(cleanTankLevel, 'clean') }}</dd>
      </div>
      <div class="metric-tile">
        <dt>Уровень раствора</dt>
        <dd>{{ levelLabel(nutrientTankLevel, 'solution') }}</dd>
      </div>
      <div
        v-if="bufferTankLevel !== null"
        class="metric-tile"
      >
        <dt>Буфер</dt>
        <dd>{{ levelLabel(bufferTankLevel) }}</dd>
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

    <p class="text-xs text-[color:var(--text-muted)]">
      Показания из полученного снимка. Признаки процесса ниже не являются измерением расхода.
    </p>
    <div
      v-if="activeChips.length > 0"
      class="flex flex-wrap gap-1.5"
    >
      <span
        v-for="chip in activeChips"
        :key="chip.key"
        class="rounded-full border px-2 py-0.5 text-[10px] font-medium"
        :class="chip.active ? 'border-[color:var(--border-muted)] text-[color:var(--text-muted)]' : 'border-[color:var(--border-muted)]/50 text-[color:var(--text-dim)]'"
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
  cleanTankLevel: number | null
  nutrientTankLevel: number | null
  bufferTankLevel: number | null
  isPumpInActive: boolean
  isCirculationActive: boolean
  isPhCorrectionActive: boolean
  isEcCorrectionActive: boolean
  isIrrigationActive: boolean
}

const props = defineProps<Props>()

const ph = computed(() => props.automationState?.current_levels?.ph ?? null)
const ec = computed(() => props.automationState?.current_levels?.ec ?? null)

const activeChips = computed(() => [
  { key: 'pump', label: 'Насос', active: props.isPumpInActive },
  { key: 'circ', label: 'Рециркуляция', active: props.isCirculationActive },
  { key: 'ph', label: 'Коррекция pH', active: props.isPhCorrectionActive },
  { key: 'ec', label: 'Коррекция EC', active: props.isEcCorrectionActive },
  { key: 'irr', label: 'Полив', active: props.isIrrigationActive },
].filter((chip) => chip.active))

function levelLabel(value: number | null, tank?: 'clean' | 'solution'): string {
  const node = props.automationState?.irr_node_state
  const max = tank === 'clean' ? node?.clean_level_max : tank === 'solution' ? node?.solution_level_max : null
  const min = tank === 'clean' ? node?.clean_level_min : tank === 'solution' ? node?.solution_level_min : null
  if (max === true) return 'Достигнута верхняя отметка'
  if (max === false && min === false) return 'Ниже нижней отметки'
  if (min === true) return 'Выше нижней отметки'
  return value == null || !Number.isFinite(value) ? 'Нет данных' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`
}

function formatMetric(value: number | null, suffix = ''): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—'
  }
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)}${suffix}`
}
</script>

<style scoped>
.metric-tile {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  padding: 0.5rem 0.65rem;
}

.metric-tile dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.metric-tile dd {
  margin-top: 0.15rem;
  font-size: 0.95rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
