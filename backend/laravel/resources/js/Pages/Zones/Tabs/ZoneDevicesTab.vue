<template>
  <div class="space-y-4">
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
      <UnassignedNodeErrorsWidget :zone-id="zone.id" :limit="5" />
    </div>
  </div>
</template>

<script setup lang="ts">
import ZoneDevicesVisualization from '@/Components/ZoneDevicesVisualization.vue'
import UnassignedNodeErrorsWidget from '@/Components/UnassignedNodeErrorsWidget.vue'
import type { Device, Zone } from '@/types'

interface Props {
  zone: Zone
  devices: Device[]
  canManageDevices: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'attach'): void
  (e: 'configure', device: Device): void
}>()
</script>
