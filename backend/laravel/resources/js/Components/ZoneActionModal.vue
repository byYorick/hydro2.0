<template>
  <Modal :open="show" :title="title" @close="$emit('close')">
    
    <form @submit.prevent="onSubmit" class="space-y-4">
      <!-- Динамические поля на основе actionType -->
      <div v-if="actionType === 'FORCE_IRRIGATION'" class="space-y-3">
        <div>
          <label for="zone-action-duration-sec" class="block text-sm font-medium mb-1">Длительность полива (секунды)</label>
          <input
            id="zone-action-duration-sec"
            name="duration_sec"
            v-model.number="form.duration_sec"
            type="number"
            min="1"
            max="3600"
            step="1"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="10"
          />
          <div class="text-xs text-neutral-400 mt-1">От 1 до 3600 секунд</div>
        </div>
      </div>

      <div v-else-if="actionType === 'FORCE_PH_CONTROL'" class="space-y-3">
        <div>
          <label for="zone-action-target-ph" class="block text-sm font-medium mb-1">Целевой pH</label>
          <input
            id="zone-action-target-ph"
            name="target_ph"
            v-model.number="form.target_ph"
            type="number"
            min="4.0"
            max="9.0"
            step="0.1"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="6.0"
          />
          <div class="text-xs text-neutral-400 mt-1">От 4.0 до 9.0</div>
        </div>
      </div>

      <div v-else-if="actionType === 'FORCE_EC_CONTROL'" class="space-y-3">
        <div>
          <label for="zone-action-target-ec" class="block text-sm font-medium mb-1">Целевой EC</label>
          <input
            id="zone-action-target-ec"
            name="target_ec"
            v-model.number="form.target_ec"
            type="number"
            min="0.1"
            max="10.0"
            step="0.1"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="1.5"
          />
          <div class="text-xs text-neutral-400 mt-1">От 0.1 до 10.0</div>
        </div>
      </div>

      <div v-else-if="actionType === 'FORCE_CLIMATE'" class="space-y-3">
        <div>
          <label for="zone-action-target-temp" class="block text-sm font-medium mb-1">Целевая температура (°C)</label>
          <input
            id="zone-action-target-temp"
            name="target_temp"
            v-model.number="form.target_temp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="22"
          />
          <div class="text-xs text-neutral-400 mt-1">От 10 до 35°C</div>
        </div>
        <div>
          <label for="zone-action-target-humidity" class="block text-sm font-medium mb-1">Целевая влажность (%)</label>
          <input
            id="zone-action-target-humidity"
            name="target_humidity"
            v-model.number="form.target_humidity"
            type="number"
            min="30"
            max="90"
            step="1"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="60"
          />
          <div class="text-xs text-neutral-400 mt-1">От 30 до 90%</div>
        </div>
      </div>

      <div v-else-if="actionType === 'FORCE_LIGHTING'" class="space-y-3">
        <div>
          <label for="zone-action-intensity" class="block text-sm font-medium mb-1">Интенсивность (%)</label>
          <input
            id="zone-action-intensity"
            name="intensity"
            v-model.number="form.intensity"
            type="number"
            min="0"
            max="100"
            step="1"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="80"
          />
          <div class="text-xs text-neutral-400 mt-1">От 0 до 100%</div>
        </div>
        <div>
          <label for="zone-action-duration-hours" class="block text-sm font-medium mb-1">Длительность (часы)</label>
          <input
            id="zone-action-duration-hours"
            name="duration_hours"
            v-model.number="form.duration_hours"
            type="number"
            min="0.5"
            max="24"
            step="0.5"
            required
            class="w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm"
            placeholder="12"
          />
          <div class="text-xs text-neutral-400 mt-1">От 0.5 до 24 часов</div>
        </div>
      </div>

      <div v-else class="text-sm text-neutral-400">
        Параметры для этого действия не требуются
      </div>

      <div v-if="error" class="text-sm text-red-400">{{ error }}</div>
    </form>
    
    <template #footer>
      <Button type="button" variant="secondary" @click="$emit('close')" :disabled="loading">
        Отмена
      </Button>
      <Button type="button" @click="onSubmit" :disabled="loading">
        {{ loading ? 'Отправка...' : 'Отправить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { useFormValidation } from '@/composables/useFormValidation'
import { VALIDATION_RANGES, VALIDATION_MESSAGES } from '@/constants/validation'
import type { CommandType } from '@/types'

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
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  defaultParams: () => ({})
})

const emit = defineEmits<{
  close: []
  submit: [data: { actionType: ActionType; params: ActionParams }]
}>()

const loading = ref<boolean>(false)
const error = ref<string | null>(null)

// Создаем мок-форму для использования useFormValidation
const mockForm = {
  errors: {} as Record<string, string>,
  clearErrors: () => {},
} as any

const { validateNumberRange } = useFormValidation(mockForm)

// Форма с параметрами по умолчанию
const form = ref<ActionParams>({
  duration_sec: 10,
  target_ph: 6.0,
  target_ec: 1.5,
  target_temp: 22,
  target_humidity: 60,
  intensity: 80,
  duration_hours: 12,
  ...props.defaultParams
})

// Заголовок и описание в зависимости от типа действия
const title = computed<string>(() => {
  const titles: Record<ActionType, string> = {
    'FORCE_IRRIGATION': 'Полив зоны',
    'FORCE_PH_CONTROL': 'Коррекция pH',
    'FORCE_EC_CONTROL': 'Коррекция EC',
    'FORCE_CLIMATE': 'Управление климатом',
    'FORCE_LIGHTING': 'Управление освещением'
  }
  return titles[props.actionType] || 'Действие'
})

const description = computed<string>(() => {
  const descriptions: Record<ActionType, string> = {
    'FORCE_IRRIGATION': 'Укажите длительность полива в секундах',
    'FORCE_PH_CONTROL': 'Укажите целевое значение pH',
    'FORCE_EC_CONTROL': 'Укажите целевое значение EC',
    'FORCE_CLIMATE': 'Укажите целевые параметры температуры и влажности',
    'FORCE_LIGHTING': 'Укажите параметры освещения'
  }
  return descriptions[props.actionType] || 'Выполнить действие'
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
      ...props.defaultParams
    }
  }
})

function onSubmit(): void {
  error.value = null

  // Валидация полей с использованием useFormValidation
  if (props.actionType === 'FORCE_IRRIGATION') {
    const validationError = validateNumberRange(
      form.value.duration_sec,
      VALIDATION_RANGES.IRRIGATION_DURATION.min,
      VALIDATION_RANGES.IRRIGATION_DURATION.max,
      'Длительность полива'
    )
    if (validationError) {
      error.value = VALIDATION_MESSAGES.IRRIGATION_DURATION
      return
    }
  } else if (props.actionType === 'FORCE_PH_CONTROL') {
    const validationError = validateNumberRange(
      form.value.target_ph,
      VALIDATION_RANGES.PH.min,
      VALIDATION_RANGES.PH.max,
      'pH'
    )
    if (validationError) {
      error.value = VALIDATION_MESSAGES.PH
      return
    }
  } else if (props.actionType === 'FORCE_EC_CONTROL') {
    const validationError = validateNumberRange(
      form.value.target_ec,
      VALIDATION_RANGES.EC.min,
      VALIDATION_RANGES.EC.max,
      'EC'
    )
    if (validationError) {
      error.value = VALIDATION_MESSAGES.EC
      return
    }
  } else if (props.actionType === 'FORCE_CLIMATE') {
    const tempError = validateNumberRange(
      form.value.target_temp,
      VALIDATION_RANGES.TEMPERATURE.min,
      VALIDATION_RANGES.TEMPERATURE.max,
      'Температура'
    )
    if (tempError) {
      error.value = VALIDATION_MESSAGES.TEMPERATURE
      return
    }
    const humidityError = validateNumberRange(
      form.value.target_humidity,
      VALIDATION_RANGES.HUMIDITY.min,
      VALIDATION_RANGES.HUMIDITY.max,
      'Влажность'
    )
    if (humidityError) {
      error.value = VALIDATION_MESSAGES.HUMIDITY
      return
    }
  } else if (props.actionType === 'FORCE_LIGHTING') {
    const intensityError = validateNumberRange(
      form.value.intensity,
      VALIDATION_RANGES.LIGHTING_INTENSITY.min,
      VALIDATION_RANGES.LIGHTING_INTENSITY.max,
      'Интенсивность'
    )
    if (intensityError) {
      error.value = VALIDATION_MESSAGES.LIGHTING_INTENSITY
      return
    }
    const durationError = validateNumberRange(
      form.value.duration_hours,
      VALIDATION_RANGES.LIGHTING_DURATION.min,
      VALIDATION_RANGES.LIGHTING_DURATION.max,
      'Длительность освещения'
    )
    if (durationError) {
      error.value = VALIDATION_MESSAGES.LIGHTING_DURATION
      return
    }
  }

  // Формируем параметры в зависимости от типа действия
  const params: ActionParams = {}
  
  if (props.actionType === 'FORCE_IRRIGATION') {
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
    params
  })
  
  emit('close')
}
</script>

