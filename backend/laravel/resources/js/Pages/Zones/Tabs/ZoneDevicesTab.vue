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
      <ZoneBindingsPanel
        :zone-id="zone.id"
        :can-manage="canManageDevices"
      />
    </div>
    <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-xl p-2">
      <div class="flex flex-wrap items-center justify-between gap-3 p-3">
        <p class="text-sm text-[color:var(--text-muted)]">
          Калибровка, коэффициенты PID и история коррекции находятся в разделе «Раствор».
        </p>
        <Link
          :href="`/zones/${zone.id}?tab=automation&auto=solution#zone-pid-config-panel-shared`"
          class="btn btn-secondary text-sm"
        >
          Настройки коррекции и PID
        </Link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import { Link } from '@inertiajs/vue3'
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
