<template>
  <Modal
    :open="show"
    :title="title"
    @close="$emit('close')"
  >
    <form
      class="space-y-4"
      data-testid="zone-command-form"
      @submit.prevent="onSubmit"
    >
      <!-- Динамические поля на основе actionType -->
      <div
        v-if="actionType === 'START_IRRIGATION' || actionType === 'FORCE_IRRIGATION'"
        class="space-y-3"
      >
        <div>
          <label
            for="zone-action-duration-sec"
            class="block text-sm font-medium mb-1"
          >Длительность полива (секунды)</label>
          <input
            id="zone-action-duration-sec"
            v-model.number="form.duration_sec"
            name="duration_sec"
            type="number"
            min="1"
            max="3600"
            step="1"
            required
            class="input-field w-full"
            :placeholder="String(defaultIrrigationDuration)"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            По умолчанию: системная настройка или длительность из фазы рецепта (если задана). Диапазон 1–3600 с.
          </div>
        </div>

        <IrrigationCorrectionSummaryPanel :summary="irrigationCorrectionSummary" />
      </div>

      <div
        v-else-if="actionType === 'FORCE_PH_CONTROL'"
        class="space-y-3"
      >
        <div>
          <label
            for="zone-action-target-ph"
            class="block text-sm font-medium mb-1"
          >Целевой pH</label>
          <input
            id="zone-action-target-ph"
            v-model.number="form.target_ph"
            name="target_ph"
            type="number"
            min="4.0"
            max="9.0"
            step="0.1"
            required
            class="input-field w-full"
            placeholder="6.0"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 4.0 до 9.0
          </div>
        </div>
      </div>

      <div
        v-else-if="actionType === 'FORCE_EC_CONTROL'"
        class="space-y-3"
      >
        <div>
          <label
            for="zone-action-target-ec"
            class="block text-sm font-medium mb-1"
          >Целевой EC</label>
          <input
            id="zone-action-target-ec"
            v-model.number="form.target_ec"
            name="target_ec"
            type="number"
            min="0.1"
            max="10.0"
            step="0.1"
            required
            class="input-field w-full"
            placeholder="1.5"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 0.1 до 10.0
          </div>
        </div>
      </div>

      <div
        v-else-if="actionType === 'FORCE_CLIMATE'"
        class="space-y-3"
      >
        <div>
          <label
            for="zone-action-target-temp"
            class="block text-sm font-medium mb-1"
          >Целевая температура (°C)</label>
          <input
            id="zone-action-target-temp"
            v-model.number="form.target_temp"
            name="target_temp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            required
            class="input-field w-full"
            placeholder="22"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 10 до 35°C
          </div>
        </div>
        <div>
          <label
            for="zone-action-target-humidity"
            class="block text-sm font-medium mb-1"
          >Целевая влажность (%)</label>
          <input
            id="zone-action-target-humidity"
            v-model.number="form.target_humidity"
            name="target_humidity"
            type="number"
            min="30"
            max="90"
            step="1"
            required
            class="input-field w-full"
            placeholder="60"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 30 до 90%
          </div>
        </div>
      </div>

      <div
        v-else-if="actionType === 'FORCE_LIGHTING'"
        class="space-y-3"
      >
        <div>
          <label
            for="zone-action-intensity"
            class="block text-sm font-medium mb-1"
          >Интенсивность (%)</label>
          <input
            id="zone-action-intensity"
            v-model.number="form.intensity"
            name="intensity"
            type="number"
            min="0"
            max="100"
            step="1"
            required
            class="input-field w-full"
            placeholder="80"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 0 до 100%
          </div>
        </div>
        <div>
          <label
            for="zone-action-duration-hours"
            class="block text-sm font-medium mb-1"
          >Длительность (часы)</label>
          <input
            id="zone-action-duration-hours"
            v-model.number="form.duration_hours"
            name="duration_hours"
            type="number"
            min="0.5"
            max="24"
            step="0.5"
            required
            class="input-field w-full"
            placeholder="12"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            От 0.5 до 24 часов
          </div>
        </div>
      </div>

      <div
        v-else
        class="text-sm text-[color:var(--text-dim)]"
      >
        Параметры для этого действия не требуются
      </div>

      <div
        v-if="error"
        class="text-sm text-[color:var(--accent-red)]"
      >
        {{ error }}
      </div>
    </form>
    
    <template #footer>
      <Button
        type="button"
        variant="secondary"
        :disabled="loading"
        @click="$emit('close')"
      >
        Отмена
      </Button>
      <Button
        type="button"
        :disabled="loading"
        @click="onSubmit"
      >
        {{ loading ? 'Отправка...' : 'Отправить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import IrrigationCorrectionSummaryPanel from '@/Components/IrrigationCorrectionSummaryPanel.vue'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import { validateNumberRange } from '@/utils/validation'
import { VALIDATION_RANGES } from '@/constants/validation'
import type { CommandType, IrrigationCorrectionSummary } from '@/types'

type ActionType = CommandType

interface ActionParams {
  duration_sec?: number
  target_ph?: number
  target_ec?: number
  target_temp?: number
  target_humidity?: number
  intensity?: number
  duration_hours?: number
}

interface Props {
  show?: boolean
  actionType: ActionType
  zoneId: number
  defaultParams?: ActionParams
  irrigationCorrectionSummary?: IrrigationCorrectionSummary | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  defaultParams: () => ({}),
  irrigationCorrectionSummary: null,
  loading: false,
})

const emit = defineEmits<{
  close: []
  submit: [data: { actionType: ActionType; params: ActionParams }]
}>()

const error = ref<string | null>(null)
const automationDefaults = useAutomationDefaults()

function resolveDefaultIrrigationDurationSec(): number {
  const fromParams = props.defaultParams?.duration_sec
  if (typeof fromParams === 'number' && Number.isFinite(fromParams) && fromParams >= 1) {
    return Math.min(3600, Math.max(1, Math.round(fromParams)))
  }
  return Math.min(
    3600,
    Math.max(1, Math.round(automationDefaults.value.water_manual_irrigation_sec)),
  )
}

const defaultIrrigationDuration = computed(() => resolveDefaultIrrigationDurationSec())

// Форма с параметрами по умолчанию
const form = ref<ActionParams>({
  duration_sec: 10,
  target_ph: 6.0,
  target_ec: 1.5,
  target_temp: 22,
  target_humidity: 60,
  intensity: 80,
  duration_hours: 12,
  ...props.defaultParams,
})
if (props.actionType === 'START_IRRIGATION' || props.actionType === 'FORCE_IRRIGATION') {
  form.value.duration_sec = resolveDefaultIrrigationDurationSec()
}

const title = computed<string>(() => {
  const titles: Record<ActionType, string> = {
    'START_IRRIGATION': 'Полив зоны',
    'FORCE_IRRIGATION': 'Полив зоны',
    'FORCE_PH_CONTROL': 'Коррекция pH',
    'FORCE_EC_CONTROL': 'Коррекция EC',
    'FORCE_CLIMATE': 'Управление климатом',
    'FORCE_LIGHTING': 'Управление освещением'
  }
  return titles[props.actionType] || 'Действие'
})

// Сброс формы при открытии модального окна
watch(() => props.show, (newVal: boolean) => {
  if (newVal) {
    error.value = null
    form.value = {
      duration_sec: 10,
      target_ph: 6.0,
      target_ec: 1.5,
      target_temp: 22,
      target_humidity: 60,
      intensity: 80,
      duration_hours: 12,
      ...props.defaultParams,
    }
    if (props.actionType === 'START_IRRIGATION' || props.actionType === 'FORCE_IRRIGATION') {
      form.value.duration_sec = resolveDefaultIrrigationDurationSec()
    }
  }
})

function onSubmit(): void {
  error.value = null

  if (props.actionType === 'START_IRRIGATION' || props.actionType === 'FORCE_IRRIGATION') {
    const err = validateNumberRange(
      form.value.duration_sec,
      VALIDATION_RANGES.IRRIGATION_DURATION.min,
      VALIDATION_RANGES.IRRIGATION_DURATION.max,
      'Длительность (сек)',
    )
    if (err) { error.value = err; return }
  } else if (props.actionType === 'FORCE_PH_CONTROL') {
    const err = validateNumberRange(form.value.target_ph, VALIDATION_RANGES.PH.min, VALIDATION_RANGES.PH.max, 'pH')
    if (err) { error.value = err; return }
  } else if (props.actionType === 'FORCE_EC_CONTROL') {
    const err = validateNumberRange(form.value.target_ec, VALIDATION_RANGES.EC.min, VALIDATION_RANGES.EC.max, 'EC')
    if (err) { error.value = err; return }
  } else if (props.actionType === 'FORCE_CLIMATE') {
    const tempErr = validateNumberRange(
      form.value.target_temp,
      VALIDATION_RANGES.TEMPERATURE.min,
      VALIDATION_RANGES.TEMPERATURE.max,
      'Температура (°C)',
    )
    if (tempErr) { error.value = tempErr; return }
    const humErr = validateNumberRange(
      form.value.target_humidity,
      VALIDATION_RANGES.HUMIDITY.min,
      VALIDATION_RANGES.HUMIDITY.max,
      'Влажность (%)',
    )
    if (humErr) { error.value = humErr; return }
  } else if (props.actionType === 'FORCE_LIGHTING') {
    const intErr = validateNumberRange(
      form.value.intensity,
      VALIDATION_RANGES.LIGHTING_INTENSITY.min,
      VALIDATION_RANGES.LIGHTING_INTENSITY.max,
      'Интенсивность (%)',
    )
    if (intErr) { error.value = intErr; return }
    const durErr = validateNumberRange(
      form.value.duration_hours,
      VALIDATION_RANGES.LIGHTING_DURATION.min,
      VALIDATION_RANGES.LIGHTING_DURATION.max,
      'Длительность (ч)',
    )
    if (durErr) { error.value = durErr; return }
  }

  // Формируем параметры в зависимости от типа действия
  const params: ActionParams = {}
  
  if (props.actionType === 'START_IRRIGATION' || props.actionType === 'FORCE_IRRIGATION') {
    params.duration_sec = form.value.duration_sec
  } else if (props.actionType === 'FORCE_PH_CONTROL') {
    params.target_ph = form.value.target_ph
  } else if (props.actionType === 'FORCE_EC_CONTROL') {
    params.target_ec = form.value.target_ec
  } else if (props.actionType === 'FORCE_CLIMATE') {
    params.target_temp = form.value.target_temp
    params.target_humidity = form.value.target_humidity
  } else if (props.actionType === 'FORCE_LIGHTING') {
    params.intensity = form.value.intensity
    params.duration_hours = form.value.duration_hours
  }

  emit('submit', {
    actionType: props.actionType,
    params,
  })
}
</script>
