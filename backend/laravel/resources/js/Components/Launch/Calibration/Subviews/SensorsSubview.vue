<template>
  <div class="flex flex-col gap-3.5">
    <SensorCalibrationStatus
      :zone-id="zoneId"
      :settings="settings"
    />
    <Hint :show="showHints">
      Двухточечная калибровка буферами (pH 4.01 / 6.86, EC 1.413). AE3
      сохраняет offset/slope и применяет их к каждому raw-значению из
      mqtt-bridge.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

defineProps<{
  zoneId: number
  settings: SensorCalibrationSettings | null
}>()

const { showHints } = useLaunchPreferences()
</script>
