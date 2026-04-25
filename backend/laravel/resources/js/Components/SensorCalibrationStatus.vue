<template>
  <ShellCard title="Калибровка сенсоров">
    <template #actions>
      <Button
        size="sm"
        variant="secondary"
        :disabled="loading"
        @click="loadStatus"
      >
        ↻ Обновить
      </Button>
    </template>

    <div class="flex flex-col gap-3.5">
      <div
        v-if="loading"
        class="text-sm text-[var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else-if="items.length === 0"
        class="text-sm text-[var(--text-dim)]"
      >
        В зоне не найдены pH/EC sensor channels.
      </div>

      <div
        v-else
        class="grid gap-3 md:grid-cols-2"
      >
        <div
          v-for="item in items"
          :key="item.node_channel_id"
          class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] p-3 flex flex-col gap-2.5"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 text-sm font-medium">
                <Ic
                  :name="item.sensor_type === 'ph' ? 'beaker' : 'wave'"
                  class="text-brand"
                />
                <span class="font-mono">{{ item.sensor_type.toUpperCase() }}</span>
                <span class="text-[var(--text-dim)]">·</span>
                <span class="font-mono text-[var(--text-muted)]">{{ item.channel_uid }}</span>
              </div>
              <div class="text-[11px] text-[var(--text-dim)] mt-1 truncate font-mono">
                {{ item.node_uid || 'unknown node' }}
              </div>
            </div>
            <Chip :tone="statusTone(item.calibration_status)">
              <template #icon>
                <span class="font-mono text-[11px]">{{ statusIcon(item.calibration_status) }}</span>
              </template>
              {{ item.calibration_status }}
            </Chip>
          </div>

          <div class="text-[11px] text-[var(--text-dim)] font-mono">
            <span v-if="item.last_calibrated_at">
              Последняя калибровка: {{ formatDate(item.last_calibrated_at) }}
            </span>
            <span v-else>Калибровка ещё не выполнялась</span>
          </div>

          <div class="flex gap-1.5 flex-wrap">
            <Button
              size="sm"
              variant="primary"
              @click="openWizard(item)"
            >
              ▶ Калибровать
            </Button>
            <Button
              size="sm"
              variant="secondary"
              @click="openHistory(item)"
            >
              История
            </Button>
          </div>
        </div>
      </div>
    </div>

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
            <Chip :tone="recordTone(record.status)">{{ record.status }}</Chip>
            <span class="font-mono text-[var(--text-dim)] text-[11px]">{{ formatDate(record.created_at) }}</span>
          </div>
          <div class="text-[11px] text-[var(--text-dim)] mt-1.5 font-mono">
            point1={{ record.point_1_reference ?? 'n/a' }} ·
            point2={{ record.point_2_reference ?? 'n/a' }}
          </div>
        </div>
      </div>
    </Modal>

    <SensorCalibrationWizard
      v-if="wizardItem"
      :open="wizardOpen"
      :zone-id="zoneId"
      :overview="wizardItem"
      :settings="settings"
      @close="wizardOpen = false"
      @completed="onWizardCompleted"
    />
  </ShellCard>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import SensorCalibrationWizard from '@/Components/SensorCalibrationWizard.vue'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import { Chip } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import Ic from '@/Components/Icons/Ic.vue'
import { useSensorCalibration } from '@/composables/useSensorCalibration'
import type {
  SensorCalibration,
  SensorCalibrationOverview,
} from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = defineProps<{
  zoneId: number
  settings: SensorCalibrationSettings
}>()

const { fetchStatus, fetchHistory } = useSensorCalibration(props.zoneId)

const loading = ref(true)
const items = ref<SensorCalibrationOverview[]>([])
const historyOpen = ref(false)
const historyLoading = ref(false)
const history = ref<SensorCalibration[]>([])
const wizardOpen = ref(false)
const wizardItem = ref<SensorCalibrationOverview | null>(null)

function statusTone(status: SensorCalibrationOverview['calibration_status']): ChipTone {
  if (status === 'ok') return 'growth'
  if (status === 'warning') return 'warn'
  if (status === 'critical') return 'alert'
  return 'neutral'
}

function statusIcon(status: SensorCalibrationOverview['calibration_status']): string {
  if (status === 'ok') return '✓'
  if (status === 'critical') return '!'
  return '·'
}

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

async function loadStatus(): Promise<void> {
  loading.value = true
  try {
    items.value = await fetchStatus()
  } finally {
    loading.value = false
  }
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

function openWizard(item: SensorCalibrationOverview): void {
  wizardItem.value = item
  wizardOpen.value = true
}

async function onWizardCompleted(): Promise<void> {
  await loadStatus()
}

onMounted(() => {
  void loadStatus()
})
</script>
