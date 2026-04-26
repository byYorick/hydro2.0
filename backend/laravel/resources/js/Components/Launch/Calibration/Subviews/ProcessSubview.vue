<template>
  <div class="flex flex-col gap-3.5">
    <ProcessCalibrationPanel
      :zone-id="zoneId"
      @saved="$emit('saved')"
    />
    <Hint :show="showHints">
      PUT <span class="font-mono">/api/automation-configs/zone/{'{id}'}/zone.process_calibration.{'{mode}'}</span>.
      Коэффициенты определяют, как AE3 прогнозирует реакцию раствора
      на дозу для 4 фаз: solution_fill / tank_recirc / irrigation / generic.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'

defineProps<{ zoneId: number }>()
defineEmits<{ (e: 'saved'): void }>()

const { showHints } = useLaunchPreferences()
</script>
