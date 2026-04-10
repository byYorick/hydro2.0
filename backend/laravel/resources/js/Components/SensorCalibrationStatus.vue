<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">
            Калибровка сенсоров
          </div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            pH/EC calibration tracking и запуск калибровки через backend.
          </div>
        </div>
        <Button
          size="sm"
          variant="secondary"
          :disabled="loading"
          @click="loadStatus"
        >
          Обновить
        </Button>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else-if="items.length === 0"
        class="text-sm text-[color:var(--text-dim)]"
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
          class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-sm font-medium">
                {{ item.sensor_type.toUpperCase() }} · {{ item.channel_uid }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                {{ item.node_uid || 'unknown node' }}
              </div>
            </div>
            <Badge :variant="badgeVariant(item.calibration_status)">
              {{ item.calibration_status }}
            </Badge>
          </div>

          <div class="text-xs text-[color:var(--text-dim)]">
            <span v-if="item.last_calibrated_at">
              Последняя калибровка: {{ formatDate(item.last_calibrated_at) }}
            </span>
            <span v-else>Калибровка ещё не выполнялась</span>
          </div>

          <div class="flex gap-2">
            <Button
              size="sm"
              @click="openWizard(item)"
            >
              Калибровать
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
      <div class="space-y-3">
        <div
          v-if="historyLoading"
          class="text-sm text-[color:var(--text-dim)]"
        >
          Загрузка...
        </div>
        <div
          v-else-if="history.length === 0"
          class="text-sm text-[color:var(--text-dim)]"
        >
          История пуста.
        </div>
        <div
          v-for="item in history"
          :key="item.id"
          class="rounded-lg border border-[color:var(--border-muted)] p-3 text-sm"
        >
          <div class="font-medium">
            {{ item.status }} · {{ formatDate(item.created_at) }}
          </div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            point1={{ item.point_1_reference ?? 'n/a' }} · point2={{ item.point_2_reference ?? 'n/a' }}
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
  </Card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import Modal from '@/Components/Modal.vue'
import SensorCalibrationWizard from '@/Components/SensorCalibrationWizard.vue'
import { useSensorCalibration } from '@/composables/useSensorCalibration'
import type { SensorCalibration, SensorCalibrationOverview } from '@/types/SensorCalibration'
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

function badgeVariant(status: SensorCalibrationOverview['calibration_status']): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'ok') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'critical') return 'danger'
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
