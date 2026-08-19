<template>
  <article
    class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4"
    :class="highlighted ? 'ring-1 ring-[color:var(--accent-cyan)]' : ''"
    data-testid="recipe-phase-card"
  >
    <header class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex items-start gap-2">
        <span
          class="mt-1 inline-block h-3 w-3 shrink-0 rounded-sm"
          :style="{ background: accentColor }"
        ></span>
        <div>
          <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
            {{ phase.position + 1 }}. {{ phase.name }}
          </h3>
          <p class="text-[11px] text-[color:var(--text-dim)]">
            {{ durationLabel }} · {{ dayRangeLabel }}
            <span v-if="phase.stageName"> · стадия: {{ phase.stageName }}</span>
          </p>
        </div>
      </div>

      <div class="flex flex-wrap gap-1">
        <span
          v-if="phase.dayNight.enabled"
          class="rounded-full border border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] px-2 py-0.5 text-[10px] text-[color:var(--badge-info-text)]"
        >
          День/ночь
        </span>
        <span
          v-if="phase.progressModel"
          class="rounded-full border border-[color:var(--badge-neutral-border)] bg-[color:var(--badge-neutral-bg)] px-2 py-0.5 text-[10px] text-[color:var(--badge-neutral-text)]"
        >
          {{ progressModelLabel(phase.progressModel) }}
        </span>
      </div>
    </header>

    <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      <div
        v-for="tile in metricTiles"
        :key="tile.key"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2.5 py-2"
      >
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
          {{ tile.label }}
        </div>
        <div class="font-mono text-sm text-[color:var(--text-primary)]">
          {{ tile.value }}
        </div>
        <div
          v-if="tile.hint"
          class="text-[10px] text-[color:var(--text-dim)]"
        >
          {{ tile.hint }}
        </div>
      </div>
    </div>

    <div class="mt-3 grid gap-3 lg:grid-cols-2">
      <section
        v-if="hasIrrigation || hasMist"
        class="space-y-1"
      >
        <h4 class="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-dim)]">
          Полив
        </h4>
        <p
          v-if="phase.irrigation.mode || phase.irrigation.systemType || phase.irrigation.substrateType"
          class="text-xs text-[color:var(--text-muted)]"
        >
          {{ irrigationModeLabel(phase.irrigation.mode) }} · {{ irrigationSystemLabel(phase.irrigation.systemType) }}
          <span v-if="phase.irrigation.substrateType"> · субстрат: {{ phase.irrigation.substrateType }}</span>
        </p>
        <p
          v-if="phase.irrigation.intervalSec !== null || phase.irrigation.durationSec !== null"
          class="text-xs text-[color:var(--text-muted)]"
        >
          Каждые {{ formatInterval(phase.irrigation.intervalSec) }} по {{ formatInterval(phase.irrigation.durationSec) }}
        </p>
        <p
          v-if="hasMist"
          class="text-xs text-[color:var(--text-muted)]"
        >
          Туман: {{ phase.mist.mode || '—' }} · каждые {{ formatInterval(phase.mist.intervalSec) }}
          по {{ formatInterval(phase.mist.durationSec) }}
        </p>
      </section>

      <section
        v-if="phase.lightHours !== null || phase.ppfd !== null"
        class="space-y-1"
      >
        <RecipePhotoperiodBar
          :photoperiod-hours="phase.lightHours"
          :start-time="phase.lightStartTime"
        />
        <p
          v-if="phase.ppfd !== null"
          class="text-[11px] text-[color:var(--text-dim)]"
        >
          PPFD: {{ formatNumberValue(phase.ppfd, 0) }} мкмоль/м²·с
        </p>
      </section>
    </div>

    <section
      v-if="phase.dayNight.hasData"
      class="mt-3 space-y-1"
    >
      <h4 class="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-dim)]">
        День / ночь
      </h4>
      <div class="flex flex-wrap gap-1.5">
        <span
          v-for="pair in dayNightChips"
          :key="pair.key"
          class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-0.5 font-mono text-[11px] text-[color:var(--text-muted)]"
        >
          {{ pair.label }}: {{ pair.day }} / {{ pair.night }}
        </span>
      </div>
    </section>

    <section
      v-if="phase.nutrition.hasData"
      class="mt-3 space-y-1"
    >
      <h4 class="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-dim)]">
        Питание
      </h4>
      <RecipeNutritionBar :nutrition="phase.nutrition" />
    </section>

    <section
      v-if="phase.agronomy"
      class="mt-3 space-y-0.5 border-t border-[color:var(--border-muted)] pt-2 text-[11px] text-[color:var(--text-muted)]"
    >
      <p v-if="phase.agronomy.criticalControls">
        <span class="text-[color:var(--text-dim)]">Контроль:</span> {{ phase.agronomy.criticalControls }}
      </p>
      <p v-if="phase.agronomy.riskFocus">
        <span class="text-[color:var(--text-dim)]">Риски:</span> {{ phase.agronomy.riskFocus }}
      </p>
    </section>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import RecipeNutritionBar from '@/Components/Recipes/RecipeNutritionBar.vue'
import RecipePhotoperiodBar from '@/Components/Recipes/RecipePhotoperiodBar.vue'
import {
  formatDayRange,
  formatDurationHours,
  formatInterval,
  formatNumberValue,
  formatRangeValue,
  irrigationModeLabel,
  irrigationSystemLabel,
  phaseColor,
  progressModelLabel,
  rangeHasValue,
  type RecipePhaseVisual,
  type VisualDayNightPair,
  type VisualRange,
} from '@/utils/recipeVisualization'

const props = withDefaults(
  defineProps<{
    phase: RecipePhaseVisual
    highlighted?: boolean
  }>(),
  { highlighted: false },
)

const accentColor = computed(() => phaseColor(props.phase.position))
const durationLabel = computed(() => formatDurationHours(props.phase.durationHours))
const dayRangeLabel = computed(() => formatDayRange(props.phase))
const hasMist = computed(
  () => props.phase.mist.intervalSec !== null || props.phase.mist.durationSec !== null,
)
const hasIrrigation = computed(() => {
  const irrigation = props.phase.irrigation
  return Boolean(
    irrigation.mode
      || irrigation.systemType
      || irrigation.substrateType
      || irrigation.intervalSec !== null
      || irrigation.durationSec !== null,
  )
})

interface MetricTile {
  key: string
  label: string
  value: string
  hint?: string
}

/** Цель фазы показывается крупно, коридор min–max уходит в подпись. */
function buildTile(key: string, label: string, range: VisualRange, unit: string, digits: number): MetricTile {
  const suffix = unit ? ` ${unit}` : ''
  const hasCorridor = range.min !== null || range.max !== null

  if (range.target === null) {
    return {
      key,
      label,
      value: hasCorridor ? formatRangeValue(range, unit, digits) : '—',
    }
  }

  return {
    key,
    label,
    value: `${formatNumberValue(range.target, digits)}${suffix}`,
    hint: hasCorridor ? formatRangeValue(range, unit, digits) : undefined,
  }
}

const metricTiles = computed<MetricTile[]>(() => {
  const phase = props.phase
  const tiles: MetricTile[] = [
    buildTile('ph', 'pH', phase.ph, '', 2),
    buildTile('ec', 'EC, mS/cm', phase.ec, '', 2),
    buildTile('temperature', 'Температура', phase.temperature, '°C', 1),
    buildTile('humidity', 'Влажность', phase.humidity, '%', 0),
  ]

  if (rangeHasValue(phase.co2)) {
    tiles.push(buildTile('co2', 'CO₂', phase.co2, 'ppm', 0))
  }

  if (rangeHasValue(phase.dli)) {
    tiles.push(buildTile('dli', 'DLI', phase.dli, '', 1))
  }

  if (rangeHasValue(phase.solutionTemp)) {
    tiles.push(buildTile('solution-temp', 'Раствор', phase.solutionTemp, '°C', 1))
  }

  if (phase.targetGdd !== null) {
    tiles.push({
      key: 'gdd',
      label: 'Целевой GDD',
      value: formatNumberValue(phase.targetGdd, 1),
      hint: phase.baseTempC !== null ? `база ${formatNumberValue(phase.baseTempC, 1)} °C` : undefined,
    })
  }

  return tiles
})

const dayNightChips = computed(() => {
  const dayNight = props.phase.dayNight
  const entries: Array<{ key: string; label: string; pair: VisualDayNightPair | null; digits: number }> = [
    { key: 'ph', label: 'pH', pair: dayNight.ph, digits: 2 },
    { key: 'ec', label: 'EC', pair: dayNight.ec, digits: 2 },
    { key: 'temperature', label: 'T °C', pair: dayNight.temperature, digits: 1 },
    { key: 'humidity', label: 'RH %', pair: dayNight.humidity, digits: 0 },
  ]

  return entries
    .filter((entry) => entry.pair !== null)
    .map((entry) => ({
      key: entry.key,
      label: entry.label,
      day: formatNumberValue(entry.pair?.day ?? null, entry.digits),
      night: formatNumberValue(entry.pair?.night ?? null, entry.digits),
    }))
})
</script>
