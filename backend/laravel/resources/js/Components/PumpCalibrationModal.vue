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
        <div>3. После сохранения форма автоматически переключится на следующий насос.</div>
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
          v-if="selectedCalibration"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
          data-testid="pump-calibration-current"
        >
          <div class="font-medium text-[color:var(--text-primary)]">
            Текущая калибровка канала: {{ selectedChannel?.label }}
          </div>
          <div class="mt-1">
            {{ selectedCalibration.ml_per_sec ?? '-' }} мл/сек
            · {{ selectedCalibration.actual_ml ?? '-' }} мл за {{ selectedCalibration.duration_sec ?? '-' }} сек
          </div>
          <div
            v-if="selectedCalibration.calibrated_at"
            class="mt-1 text-[color:var(--text-dim)]"
          >
            Обновлено: {{ formatDateTime(selectedCalibration.calibrated_at) }}
          </div>
        </div>

        <div
          v-if="calibratedChannels.length > 0"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3"
        >
          <div class="text-xs font-medium text-[color:var(--text-primary)]">
            Сохранённые калибровки
          </div>
          <div class="mt-2 space-y-1 text-xs text-[color:var(--text-muted)]">
            <div
              v-for="channel in calibratedChannels"
              :key="`cal-${channel.id}`"
            >
              {{ channel.label }}:
              {{ channel.calibration?.ml_per_sec ?? '-' }} мл/сек
            </div>
          </div>
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
import type { Device, PumpCalibrationConfig } from '@/types'

type PumpCalibrationComponent = 'npk' | 'calcium' | 'micro' | 'ph_up' | 'ph_down'

interface PumpChannelOption {
  id: number
  label: string
  channelName: string
  priority: number
  calibration: PumpCalibrationConfig | null
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
  saveSuccessSeq?: number
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  loadingRun: false,
  loadingSave: false,
  saveSuccessSeq: 0,
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

const componentKeywords: Record<PumpCalibrationComponent, string[]> = {
  npk: ['npk', 'part_a', 'nutrient_a', 'a'],
  calcium: ['calcium', 'cal', 'part_b', 'nutrient_b', 'b'],
  micro: ['micro', 'trace', 'part_c', 'nutrient_c', 'c'],
  ph_up: ['ph_up', 'phup', 'base', 'alkali'],
  ph_down: ['ph_down', 'phdown', 'acid'],
}

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
const persistedBindings = ref<Partial<Record<PumpCalibrationComponent, number>>>({})

const storageKey = computed(() => {
  if (!props.zoneId) {
    return null
  }
  return `zone:${props.zoneId}:pump_component_bindings`
})

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
        channelName,
        priority,
        calibration: channel.pump_calibration || null,
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

const channelById = computed(() => {
  return new Map(pumpChannels.value.map((channel) => [channel.id, channel]))
})

const selectedChannel = computed(() => {
  if (!form.node_channel_id) {
    return null
  }
  return channelById.value.get(form.node_channel_id) || null
})

const selectedCalibration = computed(() => selectedChannel.value?.calibration || null)

const calibratedChannels = computed(() => {
  return pumpChannels.value.filter((channel) => channel.calibration && Number(channel.calibration.ml_per_sec) > 0)
})

const autoComponentMap = computed<Partial<Record<PumpCalibrationComponent, number>>>(() => {
  const result: Partial<Record<PumpCalibrationComponent, number>> = {}
  const usedIds = new Set<number>()
  const components = componentOptions.map((option) => option.value)
  const availableIds = new Set(pumpChannels.value.map((channel) => channel.id))

  const assign = (component: PumpCalibrationComponent, channelId: number | null | undefined): boolean => {
    if (!channelId || !availableIds.has(channelId) || usedIds.has(channelId)) {
      return false
    }
    result[component] = channelId
    usedIds.add(channelId)
    return true
  }

  components.forEach((component) => {
    assign(component, persistedBindings.value[component])
  })

  components.forEach((component) => {
    if (result[component]) {
      return
    }

    const byCalibration = pumpChannels.value
      .filter((channel) => normalizeComponent(channel.calibration?.component) === component)
      .sort((a, b) => {
        const aTs = Date.parse(String(a.calibration?.calibrated_at || ''))
        const bTs = Date.parse(String(b.calibration?.calibrated_at || ''))
        return (Number.isFinite(bTs) ? bTs : 0) - (Number.isFinite(aTs) ? aTs : 0)
      })

    for (const candidate of byCalibration) {
      if (assign(component, candidate.id)) {
        break
      }
    }
  })

  components.forEach((component) => {
    if (result[component]) {
      return
    }

    const byKeyword = pumpChannels.value
      .map((channel) => ({
        channel,
        score: scoreComponent(channel.channelName, component),
      }))
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score || b.channel.priority - a.channel.priority)

    for (const candidate of byKeyword) {
      if (assign(component, candidate.channel.id)) {
        break
      }
    }
  })

  return result
})

watch(
  () => props.show,
  (isOpen) => {
    if (!isOpen) {
      return
    }
    loadPersistedBindings()
    formError.value = null
    ensureSelection()
  },
)

watch(
  pumpChannels,
  () => {
    ensureSelection()
  },
  { immediate: true },
)

watch(
  () => form.component,
  (component) => {
    const preferredChannelId = autoComponentMap.value[component]
    if (preferredChannelId) {
      form.node_channel_id = preferredChannelId
      return
    }

    if (!form.node_channel_id || !channelById.value.has(form.node_channel_id)) {
      form.node_channel_id = pumpChannels.value[0]?.id || null
    }
  },
)

watch(
  () => form.node_channel_id,
  (nodeChannelId) => {
    if (!nodeChannelId || !channelById.value.has(nodeChannelId)) {
      return
    }
    persistedBindings.value[form.component] = nodeChannelId
    savePersistedBindings()
  },
)

watch(
  () => props.saveSuccessSeq,
  (next, prev) => {
    if (!props.show || next <= prev) {
      return
    }
    moveToNextComponent()
  },
)

function normalizeComponent(value: unknown): PumpCalibrationComponent | null {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (raw === 'npk' || raw === 'calcium' || raw === 'micro' || raw === 'ph_up' || raw === 'ph_down') {
    return raw
  }
  if (raw === 'phup' || raw === 'base') {
    return 'ph_up'
  }
  if (raw === 'phdown' || raw === 'acid') {
    return 'ph_down'
  }
  return null
}

function scoreComponent(channelName: string, component: PumpCalibrationComponent): number {
  const lowerName = String(channelName || '').toLowerCase()
  return componentKeywords[component].reduce((score, keyword) => {
    return lowerName.includes(keyword) ? score + 10 : score
  }, 0)
}

function loadPersistedBindings(): void {
  if (typeof window === 'undefined' || !storageKey.value) {
    persistedBindings.value = {}
    return
  }

  const raw = window.localStorage.getItem(storageKey.value)
  if (!raw) {
    persistedBindings.value = {}
    return
  }

  try {
    const parsed = JSON.parse(raw) as Partial<Record<PumpCalibrationComponent, number>>
    const sanitized: Partial<Record<PumpCalibrationComponent, number>> = {}
    componentOptions.forEach(({ value }) => {
      const candidate = Number(parsed[value])
      if (Number.isInteger(candidate) && candidate > 0) {
        sanitized[value] = candidate
      }
    })
    persistedBindings.value = sanitized
  } catch {
    persistedBindings.value = {}
  }
}

function savePersistedBindings(): void {
  if (typeof window === 'undefined' || !storageKey.value) {
    return
  }
  window.localStorage.setItem(storageKey.value, JSON.stringify(persistedBindings.value))
}

function ensureSelection(): void {
  if (pumpChannels.value.length === 0) {
    form.node_channel_id = null
    return
  }

  const component = form.component
  const preferredChannelId = autoComponentMap.value[component]
  if (preferredChannelId) {
    form.node_channel_id = preferredChannelId
    return
  }

  const firstMapped = componentOptions.find((option) => autoComponentMap.value[option.value])
  if (firstMapped) {
    form.component = firstMapped.value
    form.node_channel_id = autoComponentMap.value[firstMapped.value] || null
    return
  }

  if (!form.node_channel_id || !channelById.value.has(form.node_channel_id)) {
    form.node_channel_id = pumpChannels.value[0].id
  }
}

function moveToNextComponent(): void {
  const components = componentOptions.map((option) => option.value)
  const currentIndex = components.indexOf(form.component)

  for (let offset = 1; offset <= components.length; offset += 1) {
    const component = components[(currentIndex + offset) % components.length]
    const channelId = autoComponentMap.value[component]
    if (!channelId) {
      continue
    }
    form.component = component
    form.node_channel_id = channelId
    form.actual_ml = null
    formError.value = null
    return
  }

  form.actual_ml = null
  formError.value = null
}

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

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('ru-RU')
}
</script>
