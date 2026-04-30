<template>
  <div class="space-y-2">
    <!-- Шапка: заголовок + кнопка калибровки -->
    <div class="flex items-center gap-1.5 px-1">
      <span class="font-headline text-sm font-bold text-[color:var(--text-primary)]">Устройства</span>
      <div class="ml-auto">
        <Button
          v-if="canOperateZone"
          size="sm"
          variant="outline"
          @click="$emit('open-pump-calibration')"
        >
          Калибровка насосов
        </Button>
      </div>
    </div>

    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-xl p-2">
      <ZoneDevicesVisualization
        :zone-name="zone.name"
        :zone-status="zone.status"
        :devices="devices"
        :can-manage="canManageDevices"
        @attach="$emit('attach')"
        @configure="(device) => $emit('configure', device)"
      />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-xl p-2">
      <UnassignedNodeErrorsWidget
        :zone-id="zone.id"
        :limit="5"
      />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-xl p-2">
      <ZoneBindingsPanel :zone-id="zone.id" />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-xl p-2">
      <AutomationEngine :zone-id="zone.id" />
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import ZoneDevicesVisualization from '@/Components/ZoneDevicesVisualization.vue'
import UnassignedNodeErrorsWidget from '@/Components/UnassignedNodeErrorsWidget.vue'
import ZoneBindingsPanel from '@/Components/Infrastructure/ZoneBindingsPanel.vue'
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
