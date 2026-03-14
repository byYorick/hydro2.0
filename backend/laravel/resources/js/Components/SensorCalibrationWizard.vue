<template>
  <Modal
    :open="open"
    :title="`Калибровка ${sensorLabel}`"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-sm text-[color:var(--text-muted)]">
        Канал: {{ overview.channel_uid }} · Узел: {{ overview.node_uid || 'unknown' }}
      </div>

      <div class="space-y-2">
        <div class="text-sm font-medium">Шаг 1. Подготовка</div>
        <div class="text-xs text-[color:var(--text-dim)]">
          Рекомендуемые значения: {{ defaults.point_1_value }} и {{ defaults.point_2_value }}.
        </div>
        <div
          v-if="sessionLoading"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Загрузка активной сессии...
        </div>
        <Button
          v-if="!calibration"
          size="sm"
          :disabled="busy || sessionLoading"
          @click="start"
        >
          Начать калибровку
        </Button>
      </div>

      <div
        v-if="calibration"
        class="space-y-4"
      >
        <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3">
          <div class="text-sm font-medium">Шаг 2. Точка 1</div>
          <label class="text-xs text-[color:var(--text-muted)] block">
            Reference value
            <input
              v-model.number="point1Value"
              type="number"
              step="0.01"
              class="input-field mt-1 w-full"
            />
          </label>
          <div class="text-xs text-[color:var(--text-dim)]">
            Статус: {{ calibration.status }}
            <span v-if="calibration.point_1_result"> · {{ calibration.point_1_result }}</span>
          </div>
          <div
            v-if="calibration.point_1_error"
            class="text-xs text-[color:var(--accent-red)]"
          >
            {{ calibration.point_1_error }}
          </div>
          <Button
            size="sm"
            :disabled="busy || calibration.status !== 'started'"
            @click="submitPoint(1)"
          >
            Калибровать точку 1
          </Button>
        </div>

        <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3">
          <div class="text-sm font-medium">Шаг 3. Точка 2</div>
          <label class="text-xs text-[color:var(--text-muted)] block">
            Reference value
            <input
              v-model.number="point2Value"
              type="number"
              step="0.01"
              class="input-field mt-1 w-full"
            />
          </label>
          <div class="text-xs text-[color:var(--text-dim)]">
            Статус: {{ calibration.status }}
            <span v-if="calibration.point_2_result"> · {{ calibration.point_2_result }}</span>
          </div>
          <div
            v-if="calibration.point_2_error"
            class="text-xs text-[color:var(--accent-red)]"
          >
            {{ calibration.point_2_error }}
          </div>
          <Button
            size="sm"
            :disabled="busy || calibration.status !== 'point_1_done'"
            @click="submitPoint(2)"
          >
            Калибровать точку 2
          </Button>
        </div>

        <div
          v-if="calibration.status === 'completed'"
          class="rounded-lg border border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] p-3 text-sm text-[color:var(--badge-success-text)]"
        >
          Калибровка завершена.
        </div>
        <div
          v-else-if="calibration.status === 'failed'"
          class="rounded-lg border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3 text-sm text-[color:var(--badge-danger-text)]"
        >
          Калибровка завершилась ошибкой. Для retry создайте новую сессию.
        </div>
      </div>

      <div class="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          @click="$emit('close')"
        >
          Закрыть
        </Button>
        <Button
          v-if="calibration && !['completed', 'failed', 'cancelled'].includes(calibration.status)"
          size="sm"
          variant="secondary"
          :disabled="busy"
          @click="cancel"
        >
          Отменить сессию
        </Button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import { useSensorCalibration } from '@/composables/useSensorCalibration'
import type { SensorCalibration, SensorCalibrationOverview } from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = defineProps<{
  open: boolean
  zoneId: number
  overview: SensorCalibrationOverview
  settings: SensorCalibrationSettings
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'completed'): void
}>()

const { startCalibration, submitPoint: submitCalibrationPoint, cancelCalibration, getCalibration } = useSensorCalibration(props.zoneId)

const calibration = ref<SensorCalibration | null>(null)
const busy = ref(false)
const sessionLoading = ref(false)
const point1Value = ref(0)
const point2Value = ref(0)
let pollHandle: number | null = null
let loadSequence = 0

const sensorLabel = computed(() => props.overview.sensor_type === 'ph' ? 'pH-сенсора' : 'EC-сенсора')
const defaults = computed(() => props.overview.sensor_type === 'ph'
  ? { point_1_value: props.settings.ph_point_1_value, point_2_value: props.settings.ph_point_2_value }
  : { point_1_value: props.settings.ec_point_1_tds, point_2_value: props.settings.ec_point_2_tds })

function stopPolling(): void {
  if (pollHandle !== null) {
    window.clearInterval(pollHandle)
    pollHandle = null
  }
}

function startPolling(): void {
  stopPolling()
  pollHandle = window.setInterval(async () => {
    if (!calibration.value) return
    const latest = await getCalibration(calibration.value.id)
    calibration.value = latest
    if (['completed', 'failed', 'cancelled', 'point_1_done'].includes(latest.status)) {
      if (['completed', 'failed', 'cancelled'].includes(latest.status)) {
        stopPolling()
        emit('completed')
      }
      if (latest.status === 'point_1_done') {
        stopPolling()
      }
    }
  }, 1500)
}

function resetSessionState(): void {
  loadSequence += 1
  stopPolling()
  calibration.value = null
  sessionLoading.value = false
  point1Value.value = defaults.value.point_1_value
  point2Value.value = defaults.value.point_2_value
}

async function hydrateActiveCalibration(): Promise<void> {
  const activeCalibrationId = props.overview.active_calibration_id
  if (!props.open || !activeCalibrationId) {
    return
  }

  const sequence = ++loadSequence
  sessionLoading.value = true
  try {
    const activeCalibration = await getCalibration(activeCalibrationId)
    if (!props.open || sequence !== loadSequence) {
      return
    }

    calibration.value = activeCalibration
    point1Value.value = activeCalibration.point_1_reference ?? defaults.value.point_1_value
    point2Value.value = activeCalibration.point_2_reference ?? defaults.value.point_2_value

    if (['point_1_pending', 'point_2_pending'].includes(activeCalibration.status)) {
      startPolling()
    }
  } finally {
    if (sequence === loadSequence) {
      sessionLoading.value = false
    }
  }
}

async function start(): Promise<void> {
  busy.value = true
  try {
    const started = await startCalibration(props.overview.node_channel_id, props.overview.sensor_type)
    calibration.value = started.calibration
    point1Value.value = started.defaults.point_1_value
    point2Value.value = started.defaults.point_2_value
  } finally {
    busy.value = false
  }
}

async function submitPoint(stage: 1 | 2): Promise<void> {
  if (!calibration.value) return
  busy.value = true
  try {
    calibration.value = await submitCalibrationPoint(
      calibration.value.id,
      stage,
      stage === 1 ? point1Value.value : point2Value.value,
    )
    startPolling()
  } finally {
    busy.value = false
  }
}

async function cancel(): Promise<void> {
  if (!calibration.value) return
  busy.value = true
  try {
    await cancelCalibration(calibration.value.id)
    stopPolling()
    emit('completed')
    emit('close')
  } finally {
    busy.value = false
  }
}

watch(
  () => [props.open, props.overview.active_calibration_id] as const,
  ([isOpen]) => {
    if (!isOpen) {
      resetSessionState()
      return
    }

    resetSessionState()
    point1Value.value = defaults.value.point_1_value
    point2Value.value = defaults.value.point_2_value
    void hydrateActiveCalibration()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>
