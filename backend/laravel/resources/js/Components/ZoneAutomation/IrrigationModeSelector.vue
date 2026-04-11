<template>
  <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionStrategy')"
      >
        Режим полива
        <select
          v-model="waterForm.irrigationDecisionStrategy"
          data-test="irrigation-decision-strategy"
          class="input-select mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        >
          <option value="task">По времени</option>
          <option value="smart_soil_v1">Умный полив</option>
        </select>
      </label>

      <div
        v-if="waterForm.irrigationDecisionStrategy === 'task'"
        class="text-xs text-[color:var(--text-muted)] md:col-span-3"
      >
        <div class="font-semibold text-[color:var(--text-primary)]">
          Параметры из текущей recipe phase
        </div>
        <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
          <div>Mode: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.mode ?? '—' }}</span></div>
          <div>Interval: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.intervalSec ?? '—' }}</span> сек</div>
          <div>Duration: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.durationSec ?? '—' }}</span> сек</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

export interface RecipeIrrigationSummary {
  mode: string | null
  intervalSec: number | null
  durationSec: number | null
}

defineProps<{
  recipeIrrigationSummary: RecipeIrrigationSummary
}>()

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const ctx = useZoneAutomationSectionContext()
</script>
