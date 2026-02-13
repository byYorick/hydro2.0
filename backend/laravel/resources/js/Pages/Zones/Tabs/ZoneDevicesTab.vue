<template>
  <div class="space-y-4">
    <div
      v-if="canOperateZone"
      class="flex justify-end"
    >
      <Button
        size="sm"
        variant="outline"
        @click="$emit('open-pump-calibration')"
      >
        Калибровка насосов
      </Button>
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <ZoneDevicesVisualization
        :zone-name="zone.name"
        :zone-status="zone.status"
        :devices="devices"
        :can-manage="canManageDevices"
        @attach="$emit('attach')"
        @configure="(device) => $emit('configure', device)"
      />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <UnassignedNodeErrorsWidget
        :zone-id="zone.id"
        :limit="5"
      />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <AutomationEngine :zone-id="zone.id" />
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import ZoneDevicesVisualization from '@/Components/ZoneDevicesVisualization.vue'
import UnassignedNodeErrorsWidget from '@/Components/UnassignedNodeErrorsWidget.vue'
import type { Device, Zone } from '@/types'

interface Props {
  zone: Zone
  devices: Device[]
  canManageDevices: boolean
  canOperateZone: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'attach'): void
  (e: 'configure', device: Device): void
  (e: 'open-pump-calibration'): void
}>()
</script>
