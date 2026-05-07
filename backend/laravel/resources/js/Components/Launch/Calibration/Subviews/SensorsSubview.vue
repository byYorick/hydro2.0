<template>
  <div class="flex flex-col gap-3.5">
    <CalibrationSensorsSubpage
      :zone-id="zoneId"
      :items="items"
      @calibrate="$emit('calibrate', $event)"
      @open-sensor-drawer="$emit('open-sensor-drawer')"
      @export-csv="$emit('export-csv')"
      @open-history="openHistory"
    />

    <Modal
      :open="historyOpen"
      title="История калибровки сенсора"
      size="large"
      @close="historyOpen = false"
    >
      <div class="flex flex-col gap-2.5">
        <div
          v-if="historyLoading"
          class="text-sm text-[var(--text-dim)]"
        >
          Загрузка...
        </div>
        <div
          v-else-if="history.length === 0"
          class="text-sm text-[var(--text-dim)]"
        >
          История пуста.
        </div>
        <div
          v-for="record in history"
          :key="record.id"
          class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] p-3 text-sm"
        >
          <div class="flex items-center gap-2 font-medium">
            <Chip :tone="recordTone(record.status)">
              {{ record.status }}
            </Chip>
            <span class="font-mono text-[var(--text-dim)] text-[11px]">{{ formatDate(record.created_at) }}</span>
          </div>
          <div class="text-[11px] text-[var(--text-dim)] mt-1.5 font-mono">
            point1={{ record.point_1_reference ?? 'n/a' }} ·
            point2={{ record.point_2_reference ?? 'n/a' }}
          </div>
        </div>
      </div>
    </Modal>

    <Hint :show="showHints">
      Двухточечная калибровка буферами (pH 4.01 / 6.86, EC 1.413). AE3
      сохраняет offset/slope и применяет их к каждому raw-значению из
      mqtt-bridge.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CalibrationSensorsSubpage from '../CalibrationSensorsSubpage.vue'
import Modal from '@/Components/Modal.vue'
import { Chip } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import { useSensorCalibration } from '@/composables/useSensorCalibration'
import type { SensorCalibration, SensorCalibrationOverview } from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = defineProps<{
  zoneId: number
  settings: SensorCalibrationSettings
  items: SensorCalibrationOverview[]
}>()

defineEmits<{
  (e: 'calibrate', item: SensorCalibrationOverview): void
  (e: 'open-sensor-drawer'): void
  (e: 'export-csv'): void
}>()

const { showHints } = useLaunchPreferences()
const { fetchHistory } = useSensorCalibration(() => props.zoneId)

const historyOpen = ref(false)
const historyLoading = ref(false)
const history = ref<SensorCalibration[]>([])

function recordTone(status: string): ChipTone {
  if (status === 'completed' || status === 'ok') return 'growth'
  if (status === 'failed' || status === 'critical') return 'alert'
  if (status === 'in_progress') return 'brand'
  return 'neutral'
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}

async function openHistory(item: SensorCalibrationOverview): Promise<void> {
  historyOpen.value = true
  historyLoading.value = true
  try {
    history.value = await fetchHistory({
      sensorType: item.sensor_type,
      nodeChannelId: item.node_channel_id,
      limit: 20,
    })
  } finally {
    historyLoading.value = false
  }
}
</script>
