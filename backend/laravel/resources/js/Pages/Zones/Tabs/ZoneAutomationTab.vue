<template>
  <div class="space-y-4">
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <AIPredictionsSection
        v-if="zoneId"
        :zone-id="zoneId"
        :targets="predictionTargets"
        :horizon-minutes="60"
        :auto-refresh="true"
        :default-expanded="true"
      />
    </div>

    <AutomationEngine
      v-if="zoneId"
      :zone-id="zoneId"
    />
    <div
      v-else
      class="text-sm text-[color:var(--text-dim)]"
    >
      Нет данных зоны для автоматизации.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import type { ZoneTargets as ZoneTargetsType } from '@/types'

type PredictionTargets = Record<string, { min?: number; max?: number }>

interface Props {
  zoneId: number | null
  targets: ZoneTargetsType | PredictionTargets
}

const props = defineProps<Props>()

const predictionTargets = computed<PredictionTargets>(() => {
  const targets = props.targets
  if (!targets || typeof targets !== 'object') return {}

  if ('ph_min' in targets || 'ec_min' in targets || 'temp_min' in targets || 'humidity_min' in targets) {
    const legacy = targets as ZoneTargetsType
    return {
      ph: { min: legacy.ph_min, max: legacy.ph_max },
      ec: { min: legacy.ec_min, max: legacy.ec_max },
      temp_air: { min: legacy.temp_min, max: legacy.temp_max },
      humidity_air: { min: legacy.humidity_min, max: legacy.humidity_max },
    }
  }

  return targets as PredictionTargets
})
</script>
