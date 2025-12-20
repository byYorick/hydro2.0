<template>
  <Modal :open="show" :title="title" @close="$emit('close')">
    <form @submit.prevent="onSubmit" class="space-y-4">
      <div v-if="hasActiveCycle" class="mb-4 p-3 rounded-md bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)]">
        <div class="text-sm text-[color:var(--badge-warning-text)] font-medium mb-1">Корректировка активного цикла</div>
        <div class="text-xs text-[color:var(--badge-warning-text)]">
          В зоне уже выполняется цикл выращивания. Изменения будут применены к текущему циклу.
        </div>
      </div>

      <!-- pH Control (обязательный) -->
      <div class="space-y-2 p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <input
              id="cycle-ph-enabled"
              v-model="form.subsystems.ph.enabled"
              type="checkbox"
              :disabled="true"
              class="w-4 h-4 rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-green)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="cycle-ph-enabled" class="text-sm font-medium">Контроль pH</label>
            <Badge variant="warning" class="text-xs">Обязательно</Badge>
          </div>
        </div>
        <div v-if="form.subsystems.ph.enabled" class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label for="cycle-ph-min" class="block text-xs text-[color:var(--text-muted)] mb-1">pH мин</label>
            <input
              id="cycle-ph-min"
              v-model.number="form.subsystems.ph.targets.min"
              type="number"
              min="4.0"
              max="9.0"
              step="0.1"
              required
              class="input-field h-8 w-full"
            />
          </div>
          <div>
            <label for="cycle-ph-max" class="block text-xs text-[color:var(--text-muted)] mb-1">pH макс</label>
            <input
              id="cycle-ph-max"
              v-model.number="form.subsystems.ph.targets.max"
              type="number"
              min="4.0"
              max="9.0"
              step="0.1"
              required
              class="input-field h-8 w-full"
            />
          </div>
        </div>
      </div>

      <!-- EC Control (обязательный) -->
      <div class="space-y-2 p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <input
              id="cycle-ec-enabled"
              v-model="form.subsystems.ec.enabled"
              type="checkbox"
              :disabled="true"
              class="w-4 h-4 rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-green)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="cycle-ec-enabled" class="text-sm font-medium">Контроль EC</label>
            <Badge variant="warning" class="text-xs">Обязательно</Badge>
          </div>
        </div>
        <div v-if="form.subsystems.ec.enabled" class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label for="cycle-ec-min" class="block text-xs text-[color:var(--text-muted)] mb-1">EC мин</label>
            <input
              id="cycle-ec-min"
              v-model.number="form.subsystems.ec.targets.min"
              type="number"
              min="0.1"
              max="10.0"
              step="0.1"
              required
              class="input-field h-8 w-full"
            />
          </div>
          <div>
            <label for="cycle-ec-max" class="block text-xs text-[color:var(--text-muted)] mb-1">EC макс</label>
            <input
              id="cycle-ec-max"
              v-model.number="form.subsystems.ec.targets.max"
              type="number"
              min="0.1"
              max="10.0"
              step="0.1"
              required
              class="input-field h-8 w-full"
            />
          </div>
        </div>
      </div>

      <!-- Climate (опциональный) -->
      <div class="space-y-2 p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <input
              id="cycle-climate-enabled"
              v-model="form.subsystems.climate.enabled"
              type="checkbox"
              class="w-4 h-4 rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-green)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="cycle-climate-enabled" class="text-sm font-medium">Климат</label>
            <Badge variant="neutral" class="text-xs">Опционально</Badge>
          </div>
        </div>
        <div v-if="form.subsystems.climate.enabled" class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label for="cycle-climate-temp" class="block text-xs text-[color:var(--text-muted)] mb-1">Температура (°C)</label>
            <input
              id="cycle-climate-temp"
              v-model.number="form.subsystems.climate.targets.temperature"
              type="number"
              min="10"
              max="35"
              step="0.5"
              :required="form.subsystems.climate.enabled"
              class="input-field h-8 w-full"
            />
          </div>
          <div>
            <label for="cycle-climate-humidity" class="block text-xs text-[color:var(--text-muted)] mb-1">Влажность (%)</label>
            <input
              id="cycle-climate-humidity"
              v-model.number="form.subsystems.climate.targets.humidity"
              type="number"
              min="30"
              max="90"
              step="1"
              :required="form.subsystems.climate.enabled"
              class="input-field h-8 w-full"
            />
          </div>
        </div>
      </div>

      <!-- Lighting (опциональный) -->
      <div class="space-y-2 p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <input
              id="cycle-lighting-enabled"
              v-model="form.subsystems.lighting.enabled"
              type="checkbox"
              class="w-4 h-4 rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-green)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="cycle-lighting-enabled" class="text-sm font-medium">Освещение</label>
            <Badge variant="neutral" class="text-xs">Опционально</Badge>
          </div>
        </div>
        <div v-if="form.subsystems.lighting.enabled" class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label for="cycle-lighting-hours-on" class="block text-xs text-[color:var(--text-muted)] mb-1">Часов включено</label>
            <input
              id="cycle-lighting-hours-on"
              v-model.number="form.subsystems.lighting.targets.hours_on"
              type="number"
              min="0"
              max="24"
              step="0.5"
              :required="form.subsystems.lighting.enabled"
              class="input-field h-8 w-full"
            />
          </div>
          <div>
            <label for="cycle-lighting-hours-off" class="block text-xs text-[color:var(--text-muted)] mb-1">Часов выключено</label>
            <input
              id="cycle-lighting-hours-off"
              v-model.number="form.subsystems.lighting.targets.hours_off"
              type="number"
              min="0"
              max="24"
              step="0.5"
              :required="form.subsystems.lighting.enabled"
              class="input-field h-8 w-full"
            />
          </div>
        </div>
      </div>

      <!-- Irrigation (обязательный) -->
      <div class="space-y-2 p-3 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <input
              id="cycle-irrigation-enabled"
              v-model="form.subsystems.irrigation.enabled"
              type="checkbox"
              :disabled="true"
              class="w-4 h-4 rounded border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--accent-green)] focus:ring-[color:var(--focus-ring)]"
            />
            <label for="cycle-irrigation-enabled" class="text-sm font-medium">Полив</label>
            <Badge variant="warning" class="text-xs">Обязательно</Badge>
          </div>
        </div>
        <div v-if="form.subsystems.irrigation.enabled" class="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label for="cycle-irrigation-interval" class="block text-xs text-[color:var(--text-muted)] mb-1">Интервал (мин)</label>
            <input
              id="cycle-irrigation-interval"
              v-model.number="form.subsystems.irrigation.targets.interval_minutes"
              type="number"
              min="5"
              max="1440"
              step="5"
              required
              class="input-field h-8 w-full"
            />
          </div>
          <div>
            <label for="cycle-irrigation-duration" class="block text-xs text-[color:var(--text-muted)] mb-1">Длительность (сек)</label>
            <input
              id="cycle-irrigation-duration"
              v-model.number="form.subsystems.irrigation.targets.duration_seconds"
              type="number"
              min="1"
              max="3600"
              step="1"
              required
              class="input-field h-8 w-full"
            />
          </div>
        </div>
      </div>

      <div v-if="error" class="text-sm text-[color:var(--accent-red)]">{{ error }}</div>
    </form>
    
    <template #footer>
      <Button type="button" variant="secondary" @click="$emit('close')" :disabled="loading">
        Отмена
      </Button>
      <Button type="button" @click="onSubmit" :disabled="loading">
        {{ loading ? 'Отправка...' : (hasActiveCycle ? 'Скорректировать цикл' : 'Запустить цикл') }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'

interface PhaseTargets {
  ph?: { min: number; max: number }
  ec?: { min: number; max: number }
  climate?: { temperature: number; humidity: number }
  lighting?: { hours_on: number; hours_off: number }
  irrigation?: { interval_minutes: number; duration_seconds: number }
}

interface ActiveCycleSubsystems {
  ph?: { enabled: boolean; targets: { min: number; max: number } | null }
  ec?: { enabled: boolean; targets: { min: number; max: number } | null }
  climate?: { enabled: boolean; targets: { temperature: number; humidity: number } | null }
  lighting?: { enabled: boolean; targets: { hours_on: number; hours_off: number } | null }
  irrigation?: { enabled: boolean; targets: { interval_minutes: number; duration_seconds: number } | null }
}

interface Props {
  show?: boolean
  zoneId: number
  currentPhaseTargets?: PhaseTargets | null
  activeCycle?: { subsystems?: ActiveCycleSubsystems } | null
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  currentPhaseTargets: null,
  activeCycle: null
})

const emit = defineEmits<{
  close: []
  submit: [data: { mode: 'start' | 'adjust'; subsystems: Record<string, { enabled: boolean; targets: any }> }]
}>()

const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const hasActiveCycle = computed(() => props.activeCycle !== null)

const title = computed(() => {
  return hasActiveCycle.value ? 'Корректировка цикла выращивания' : 'Запуск цикла выращивания'
})

// Инициализация формы из current_phase.targets или active_cycle.subsystems
function initializeForm() {
  const defaults = {
    ph: {
      enabled: true,
      targets: { min: 5.8, max: 6.2 }
    },
    ec: {
      enabled: true,
      targets: { min: 1.4, max: 1.8 }
    },
    climate: {
      enabled: false,
      targets: { temperature: 24, humidity: 60 }
    },
    lighting: {
      enabled: false,
      targets: { hours_on: 18, hours_off: 6 }
    },
    irrigation: {
      enabled: true,
      targets: { interval_minutes: 30, duration_seconds: 120 }
    }
  }

  // Если есть активный цикл, используем его значения
  if (props.activeCycle?.subsystems) {
    const active = props.activeCycle.subsystems
    
    // Проверяем валидность таргетов перед использованием
    const getPhTargets = () => {
      if (active.ph?.targets && typeof active.ph.targets.min === 'number' && typeof active.ph.targets.max === 'number') {
        return active.ph.targets
      }
      return defaults.ph.targets
    }
    
    const getEcTargets = () => {
      if (active.ec?.targets && typeof active.ec.targets.min === 'number' && typeof active.ec.targets.max === 'number') {
        return active.ec.targets
      }
      return defaults.ec.targets
    }
    
    const getClimateTargets = () => {
      if (active.climate?.targets && typeof active.climate.targets.temperature === 'number' && typeof active.climate.targets.humidity === 'number') {
        return active.climate.targets
      }
      return defaults.climate.targets
    }
    
    const getLightingTargets = () => {
      if (active.lighting?.targets && typeof active.lighting.targets.hours_on === 'number') {
        return {
          hours_on: active.lighting.targets.hours_on,
          hours_off: typeof active.lighting.targets.hours_off === 'number' ? active.lighting.targets.hours_off : (24 - active.lighting.targets.hours_on)
        }
      }
      return defaults.lighting.targets
    }
    
    const getIrrigationTargets = () => {
      if (active.irrigation?.targets && typeof active.irrigation.targets.interval_minutes === 'number' && typeof active.irrigation.targets.duration_seconds === 'number') {
        return active.irrigation.targets
      }
      return defaults.irrigation.targets
    }
    
    return {
      ph: {
        enabled: active.ph?.enabled ?? true,
        targets: getPhTargets()
      },
      ec: {
        enabled: active.ec?.enabled ?? true,
        targets: getEcTargets()
      },
      climate: {
        enabled: active.climate?.enabled ?? false,
        targets: getClimateTargets()
      },
      lighting: {
        enabled: active.lighting?.enabled ?? false,
        targets: getLightingTargets()
      },
      irrigation: {
        enabled: active.irrigation?.enabled ?? true,
        targets: getIrrigationTargets()
      }
    }
  }

  // Иначе используем таргеты текущей фазы
  if (props.currentPhaseTargets) {
    const phase = props.currentPhaseTargets
    
    // Проверяем валидность таргетов перед использованием
    const getPhTargets = () => {
      if (phase.ph && typeof phase.ph.min === 'number' && typeof phase.ph.max === 'number') {
        return phase.ph
      }
      return defaults.ph.targets
    }
    
    const getEcTargets = () => {
      if (phase.ec && typeof phase.ec.min === 'number' && typeof phase.ec.max === 'number') {
        return phase.ec
      }
      return defaults.ec.targets
    }
    
    const getClimateTargets = () => {
      if (phase.climate && typeof phase.climate.temperature === 'number' && typeof phase.climate.humidity === 'number') {
        return phase.climate
      }
      return defaults.climate.targets
    }
    
    const getLightingTargets = () => {
      if (phase.lighting && typeof phase.lighting.hours_on === 'number') {
        return {
          hours_on: phase.lighting.hours_on,
          hours_off: typeof phase.lighting.hours_off === 'number' ? phase.lighting.hours_off : (24 - phase.lighting.hours_on)
        }
      }
      return defaults.lighting.targets
    }
    
    const getIrrigationTargets = () => {
      if (phase.irrigation && typeof phase.irrigation.interval_minutes === 'number' && typeof phase.irrigation.duration_seconds === 'number') {
        return phase.irrigation
      }
      return defaults.irrigation.targets
    }
    
    return {
      ph: {
        enabled: true,
        targets: getPhTargets()
      },
      ec: {
        enabled: true,
        targets: getEcTargets()
      },
      climate: {
        enabled: false,
        targets: getClimateTargets()
      },
      lighting: {
        enabled: false,
        targets: getLightingTargets()
      },
      irrigation: {
        enabled: true,
        targets: getIrrigationTargets()
      }
    }
  }

  return defaults
}

const form = ref(initializeForm())

// Сброс формы при открытии модального окна
watch(() => props.show, (newVal: boolean) => {
  if (newVal) {
    error.value = null
    form.value = initializeForm()
  }
})

// Сброс формы при изменении пропсов
watch([() => props.currentPhaseTargets, () => props.activeCycle], () => {
  if (props.show) {
    form.value = initializeForm()
  }
})

function onSubmit(): void {
  error.value = null

  // Валидация обязательных подсистем
  if (!form.value.ph.enabled || !form.value.ph.targets) {
    error.value = 'Контроль pH обязателен и должен быть включен'
    return
  }
  if (!form.value.ec.enabled || !form.value.ec.targets) {
    error.value = 'Контроль EC обязателен и должен быть включен'
    return
  }
  if (!form.value.irrigation.enabled || !form.value.irrigation.targets) {
    error.value = 'Полив обязателен и должен быть включен'
    return
  }

  // Валидация диапазонов для pH
  const phTargets = form.value.ph.targets
  if (typeof phTargets.min !== 'number' || typeof phTargets.max !== 'number') {
    error.value = 'pH: необходимо указать минимальное и максимальное значения'
    return
  }
  if (phTargets.min >= phTargets.max) {
    error.value = 'pH мин должен быть меньше pH макс'
    return
  }
  if (phTargets.min < 4.0 || phTargets.max > 9.0) {
    error.value = 'pH должен быть в диапазоне 4.0–9.0'
    return
  }

  // Валидация диапазонов для EC
  const ecTargets = form.value.ec.targets
  if (typeof ecTargets.min !== 'number' || typeof ecTargets.max !== 'number') {
    error.value = 'EC: необходимо указать минимальное и максимальное значения'
    return
  }
  if (ecTargets.min >= ecTargets.max) {
    error.value = 'EC мин должен быть меньше EC макс'
    return
  }
  if (ecTargets.min < 0.1 || ecTargets.max > 10.0) {
    error.value = 'EC должен быть в диапазоне 0.1–10.0'
    return
  }

  // Валидация опциональных подсистем (если enabled, то должны быть targets)
  if (form.value.climate.enabled) {
    if (!form.value.climate.targets) {
      error.value = 'Климат: при включении необходимо указать параметры'
      return
    }
    const climateTargets = form.value.climate.targets
    if (typeof climateTargets.temperature !== 'number' || typeof climateTargets.humidity !== 'number') {
      error.value = 'Климат: необходимо указать температуру и влажность'
      return
    }
    if (climateTargets.temperature < 10 || climateTargets.temperature > 35) {
      error.value = 'Температура должна быть в диапазоне 10–35°C'
      return
    }
    if (climateTargets.humidity < 30 || climateTargets.humidity > 90) {
      error.value = 'Влажность должна быть в диапазоне 30–90%'
      return
    }
  }

  if (form.value.lighting.enabled) {
    if (!form.value.lighting.targets) {
      error.value = 'Освещение: при включении необходимо указать параметры'
      return
    }
    const lightingTargets = form.value.lighting.targets
    if (typeof lightingTargets.hours_on !== 'number' || typeof lightingTargets.hours_off !== 'number') {
      error.value = 'Освещение: необходимо указать часы включения и паузы'
      return
    }
    if (lightingTargets.hours_on < 0 || lightingTargets.hours_on > 24) {
      error.value = 'Часы включения должны быть в диапазоне 0–24'
      return
    }
    if (lightingTargets.hours_off < 0 || lightingTargets.hours_off > 24) {
      error.value = 'Часы паузы должны быть в диапазоне 0–24'
      return
    }
  }

  // Валидация полива
  const irrigationTargets = form.value.irrigation.targets
  if (typeof irrigationTargets.interval_minutes !== 'number' || typeof irrigationTargets.duration_seconds !== 'number') {
    error.value = 'Полив: необходимо указать интервал и длительность'
    return
  }
  if (irrigationTargets.interval_minutes < 5 || irrigationTargets.interval_minutes > 1440) {
    error.value = 'Интервал полива должен быть в диапазоне 5–1440 минут'
    return
  }
  if (irrigationTargets.duration_seconds < 1 || irrigationTargets.duration_seconds > 3600) {
    error.value = 'Длительность полива должна быть в диапазоне 1–3600 секунд'
    return
  }

  // Формируем subsystems для отправки (только enabled подсистемы с targets)
  const subsystems: Record<string, { enabled: boolean; targets: any }> = {}
  
  subsystems.ph = {
    enabled: form.value.ph.enabled,
    targets: form.value.ph.enabled ? form.value.ph.targets : null
  }
  subsystems.ec = {
    enabled: form.value.ec.enabled,
    targets: form.value.ec.enabled ? form.value.ec.targets : null
  }
  subsystems.climate = {
    enabled: form.value.climate.enabled,
    targets: form.value.climate.enabled ? form.value.climate.targets : null
  }
  subsystems.lighting = {
    enabled: form.value.lighting.enabled,
    targets: form.value.lighting.enabled ? form.value.lighting.targets : null
  }
  subsystems.irrigation = {
    enabled: form.value.irrigation.enabled,
    targets: form.value.irrigation.enabled ? form.value.irrigation.targets : null
  }

  emit('submit', {
    mode: hasActiveCycle.value ? 'adjust' : 'start',
    subsystems
  })
  
  emit('close')
}
</script>
