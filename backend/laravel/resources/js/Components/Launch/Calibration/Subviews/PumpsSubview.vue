<template>
  <div class="flex flex-col gap-3.5">
    <CalibrationPumpsSubpage
      :zone-id="zoneId"
      :pumps="pumps"
      @calibrate="(p) => $emit('calibrate', p)"
      @open-pump-wizard="$emit('open-pump-wizard')"
      @export-csv="$emit('export-csv')"
    />
    <Hint :show="showHints">
      <span class="font-mono">POST /api/zones/{'{id}'}/calibrate-pump</span>
      &nbsp;· params <span class="font-mono">{'{node_channel_id, duration_sec, actual_ml, component, skip_run, manual_override}'}</span>.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import CalibrationPumpsSubpage, {
  type PumpRow,
} from '../CalibrationPumpsSubpage.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { PumpCalibration } from '@/types/PidConfig'

defineProps<{
  zoneId: number
  pumps: PumpCalibration[]
}>()

defineEmits<{
  (e: 'calibrate', pump: PumpRow): void
  (e: 'open-pump-wizard'): void
  (e: 'export-csv'): void
}>()

const { showHints } = useLaunchPreferences()
</script>
