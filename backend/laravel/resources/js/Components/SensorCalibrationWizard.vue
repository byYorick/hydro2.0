<template>
  <Teleport to="body">
    <Modal
      :open="open"
      :title="`Калибровка ${sensorLabel}`"
      size="large"
      class="z-[70]"
      @close="$emit('close')"
    >
      <SensorCalibrationWizardCore
        v-if="open"
        :zone-id="zoneId"
        :overview="overview"
        :settings="settings"
        :active="open"
        @close="$emit('close')"
        @session-finished="$emit('session-finished', $event)"
      />
    </Modal>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Modal from '@/Components/Modal.vue'
import SensorCalibrationWizardCore from '@/Components/SensorCalibrationWizardCore.vue'
import type { SensorCalibrationOverview, SensorCalibrationSessionOutcome } from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = defineProps<{
  open: boolean
  zoneId: number
  overview: SensorCalibrationOverview
  settings: SensorCalibrationSettings
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'session-finished', outcome: SensorCalibrationSessionOutcome): void
}>()

const sensorLabel = computed(() => props.overview.sensor_type === 'ph' ? 'pH-сенсора' : 'EC-сенсора')
</script>
