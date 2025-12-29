<template>
  <div class="space-y-4">
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <AIPredictionsSection
        v-if="zoneId"
        :zone-id="zoneId"
        :targets="targets"
        :horizon-minutes="60"
        :auto-refresh="true"
        :default-expanded="true"
      />
    </div>

    <AutomationEngine v-if="zoneId" :zone-id="zoneId" />
    <div v-else class="text-sm text-[color:var(--text-dim)]">Нет данных зоны для автоматизации.</div>
  </div>
</template>

<script setup lang="ts">
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import type { ZoneTargets as ZoneTargetsType } from '@/types'

interface Props {
  zoneId: number | null
  targets: ZoneTargetsType
}

defineProps<Props>()
</script>
