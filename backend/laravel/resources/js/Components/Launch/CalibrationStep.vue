<template>
  <section class="flex flex-col gap-3">
    <CalibrationHub
      v-if="zoneId"
      :zone-id="zoneId"
      :phase-targets="phaseTargets"
      @updated="$emit('calibration-updated')"
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
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'

defineProps<{
  zoneId?: number
  phaseTargets?: RecipePhasePidTargets | null
}>()

defineEmits<{
  (event: 'calibration-updated'): void
}>()
</script>
