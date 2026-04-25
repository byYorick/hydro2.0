<template>
  <section class="flex flex-col gap-3">
    <CalibrationHub
      v-if="zoneId"
      :zone-id="zoneId"
      :phase-targets="phaseTargets"
      @updated="onAuthorityUpdated"
    />
    <div
      v-else
      class="px-3 py-2.5 rounded-md border border-warn-soft bg-warn-soft text-warn text-sm"
    >
      Калибровки доступны после выбора зоны.
    </div>
  </section>
</template>

<script setup lang="ts">
import CalibrationHub from '@/Components/Launch/Calibration/CalibrationHub.vue'
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow'
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'

withDefaults(
  defineProps<{
    blockers?: LaunchFlowReadinessBlocker[]
    warnings?: string[]
    zoneId?: number
    phaseTargets?: RecipePhasePidTargets | null
  }>(),
  {
    blockers: () => [],
    warnings: () => [],
    zoneId: undefined,
    phaseTargets: null,
  },
)

const emit = defineEmits<{
  (event: 'navigate', blocker: LaunchFlowReadinessBlocker): void
  (event: 'calibration-updated'): void
}>()

function onAuthorityUpdated() {
  emit('calibration-updated')
}
</script>
