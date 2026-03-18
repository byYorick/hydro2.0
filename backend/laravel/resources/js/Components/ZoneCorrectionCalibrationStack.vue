<template>
  <div class="space-y-4">
    <section class="space-y-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Correction runtime
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Готовность runtime, tuning PID и process calibration для in-flow correction.
        </div>
      </div>

      <CorrectionRuntimeReadinessCard
        :zone-id="zoneId"
        @focus-process-calibration="scrollToSection('zone-process-calibration-panel-shared')"
        @open-pump-calibration="$emit('open-pump-calibration')"
      />
      <section class="grid gap-4 xl:grid-cols-2">
        <PidConfigForm :zone-id="zoneId" />
        <RelayAutotuneTrigger :zone-id="zoneId" />
      </section>
      <div id="zone-process-calibration-panel-shared">
        <ProcessCalibrationPanel :zone-id="zoneId" />
      </div>
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Калибровка дозирования
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Статус и история pump calibration. Runtime bounds и zone-level overrides собраны в этом общем correction/calibration stack.
        </div>
      </div>

      <PumpCalibrationsPanel
        :zone-id="zoneId"
        @open-pump-calibration="$emit('open-pump-calibration')"
      />
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Калибровка сенсоров
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Отдельный контур pH/EC sensor calibration и его история.
        </div>
      </div>

      <SensorCalibrationStatus
        :zone-id="zoneId"
        :settings="sensorCalibrationSettings"
      />
    </section>

    <section class="space-y-4 border-t border-[color:var(--border-muted)] pt-4">
      <div>
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Zone runtime overrides
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1">
          Zone-level override системных порогов pump calibration для runtime planner.
        </div>
      </div>

      <ZonePumpCalibrationSettingsCard :zone-id="zoneId" />
    </section>
  </div>
</template>

<script setup lang="ts">
import CorrectionRuntimeReadinessCard from '@/Components/CorrectionRuntimeReadinessCard.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue'
import ZonePumpCalibrationSettingsCard from '@/Components/ZonePumpCalibrationSettingsCard.vue'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

defineProps<{
  zoneId: number
  sensorCalibrationSettings: SensorCalibrationSettings
}>()

defineEmits<{
  (e: 'open-pump-calibration'): void
}>()

function scrollToSection(id: string): void {
  if (typeof document === 'undefined') {
    return
  }

  const element = document.getElementById(id)
  if (!element) {
    return
  }

  element.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>
