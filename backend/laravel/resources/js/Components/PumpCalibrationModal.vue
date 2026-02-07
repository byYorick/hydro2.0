<template>
  <Modal
    :open="show"
    title="Калибровка дозирующих насосов"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]">
        <div>1. Запустите насос на заданное время и измерьте фактический объём.</div>
        <div>2. Введите измеренный объём (мл) и сохраните калибровку в конфиг ноды.</div>
      </div>

      <div
        v-if="pumpChannels.length === 0"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-sm text-[color:var(--text-muted)]"
      >
        В зоне не найдено каналов актуаторов для калибровки.
      </div>

      <template v-else>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label class="text-xs text-[color:var(--text-muted)]">
            Компонент
            <select
              v-model="form.component"
              class="input-select mt-1 w-full"
              data-testid="pump-calibration-component"
            >
              <option
                v-for="option in componentOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Канал помпы
            <select
              v-model.number="form.node_channel_id"
              class="input-select mt-1 w-full"
              data-testid="pump-calibration-channel"
            >
              <option
                v-for="channel in pumpChannels"
                :key="channel.id"
                :value="channel.id"
              >
                {{ channel.label }}
              </option>
            </select>
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Время запуска (сек)
            <input
              v-model.number="form.duration_sec"
              type="number"
              min="1"
              max="120"
              step="1"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-duration"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Фактический объём (мл)
            <input
              v-model.number="form.actual_ml"
              type="number"
              min="0.01"
              max="100000"
              step="0.01"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-actual-ml"
            />
          </label>
        </div>

        <div
          v-if="formError"
          class="text-sm text-[color:var(--accent-red)]"
          data-testid="pump-calibration-error"
        >
          {{ formError }}
        </div>

        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            :disabled="loadingRun"
            data-testid="pump-calibration-start-btn"
            @click="onStart"
          >
            {{ loadingRun ? 'Запуск...' : 'Запустить калибровку' }}
          </Button>
          <Button
            type="button"
            :disabled="loadingSave"
            data-testid="pump-calibration-save-btn"
            @click="onSave"
          >
            {{ loadingSave ? 'Сохранение...' : 'Сохранить фактический объём' }}
          </Button>
        </div>
      </template>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import type { Device } from '@/types'

type PumpCalibrationComponent = 'npk' | 'calcium' | 'micro' | 'ph_up' | 'ph_down'

interface PumpChannelOption {
  id: number
  label: string
  priority: number
}

interface StartPumpCalibrationPayload {
  node_channel_id: number
  duration_sec: number
  component: PumpCalibrationComponent
}

interface SavePumpCalibrationPayload extends StartPumpCalibrationPayload {
  actual_ml: number
  skip_run: true
}

interface Props {
  show?: boolean
  zoneId: number | null
  devices: Device[]
  loadingRun?: boolean
  loadingSave?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  loadingRun: false,
  loadingSave: false,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'start', payload: StartPumpCalibrationPayload): void
  (e: 'save', payload: SavePumpCalibrationPayload): void
}>()

const componentOptions: Array<{ value: PumpCalibrationComponent; label: string }> = [
  { value: 'npk', label: 'NPK (комплекс)' },
  { value: 'calcium', label: 'Calcium' },
  { value: 'micro', label: 'Micro' },
  { value: 'ph_up', label: 'pH Up' },
  { value: 'ph_down', label: 'pH Down' },
]

const form = reactive<{
  component: PumpCalibrationComponent
  node_channel_id: number | null
  duration_sec: number
  actual_ml: number | null
}>({
  component: 'npk',
  node_channel_id: null,
  duration_sec: 20,
  actual_ml: null,
})

const formError = ref<string | null>(null)

const pumpChannels = computed<PumpChannelOption[]>(() => {
  const keywordPriority: Array<{ keyword: string; score: number }> = [
    { keyword: 'nutrient', score: 30 },
    { keyword: 'pump', score: 20 },
    { keyword: 'dose', score: 15 },
    { keyword: 'ph', score: 10 },
    { keyword: 'acid', score: 10 },
    { keyword: 'base', score: 10 },
  ]

  const channels: PumpChannelOption[] = []

  props.devices.forEach((device) => {
    const deviceLabel = device.uid || device.name || `Node ${device.id}`
    ;(device.channels || []).forEach((channel) => {
      const channelId = Number(channel.id)
      if (!Number.isInteger(channelId) || channelId <= 0) {
        return
      }

      const channelType = String(channel.type || '').toLowerCase()
      if (!channelType.includes('actuator')) {
        return
      }

      const channelName = String(channel.channel || '')
      const lowerName = channelName.toLowerCase()
      const priority = keywordPriority.reduce((maxScore, item) => {
        return lowerName.includes(item.keyword) ? Math.max(maxScore, item.score) : maxScore
      }, 0)

      channels.push({
        id: channelId,
        label: `${deviceLabel} / ${channelName}`,
        priority,
      })
    })
  })

  return channels.sort((a, b) => {
    if (a.priority !== b.priority) {
      return b.priority - a.priority
    }
    return a.label.localeCompare(b.label)
  })
})

watch(
  pumpChannels,
  (channels) => {
    if (channels.length === 0) {
      form.node_channel_id = null
      return
    }
    if (!channels.some((channel) => channel.id === form.node_channel_id)) {
      form.node_channel_id = channels[0].id
    }
  },
  { immediate: true },
)

watch(
  () => props.show,
  (isOpen) => {
    if (!isOpen) {
      return
    }
    formError.value = null
  },
)

function validateCommon(): string | null {
  if (!props.zoneId || props.zoneId <= 0) {
    return 'Не удалось определить зону для калибровки.'
  }
  if (!form.node_channel_id || form.node_channel_id <= 0) {
    return 'Выберите канал помпы.'
  }
  if (!Number.isFinite(form.duration_sec) || form.duration_sec < 1 || form.duration_sec > 120) {
    return 'Время запуска должно быть от 1 до 120 секунд.'
  }
  return null
}

function onStart(): void {
  const validationError = validateCommon()
  if (validationError) {
    formError.value = validationError
    return
  }

  formError.value = null
  emit('start', {
    node_channel_id: form.node_channel_id as number,
    duration_sec: Math.trunc(form.duration_sec),
    component: form.component,
  })
}

function onSave(): void {
  const validationError = validateCommon()
  if (validationError) {
    formError.value = validationError
    return
  }
  if (!Number.isFinite(form.actual_ml) || (form.actual_ml as number) <= 0) {
    formError.value = 'Введите фактический объём больше 0 мл.'
    return
  }

  formError.value = null
  emit('save', {
    node_channel_id: form.node_channel_id as number,
    duration_sec: Math.trunc(form.duration_sec),
    actual_ml: Number(form.actual_ml),
    component: form.component,
    skip_run: true,
  })
}
</script>
