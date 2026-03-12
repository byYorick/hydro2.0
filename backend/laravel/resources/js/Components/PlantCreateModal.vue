<template>
  <Modal :open="show" title="Создать растение" @close="handleClose" size="large">
    <form @submit.prevent="onSubmit" class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="md:col-span-2">
          <label for="plant-name" class="block text-xs text-neutral-400 mb-1">
            Название <span class="text-red-400">*</span>
          </label>
          <input
            id="plant-name"
            name="name"
            v-model="form.name"
            type="text"
            required
            placeholder="Салат Айсберг"
            class="h-9 w-full rounded-md border px-2 text-sm"
            :class="errors.name ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'"
            autocomplete="off"
          />
          <div v-if="errors.name" class="text-xs text-red-400 mt-1">{{ errors.name }}</div>
        </div>

        <div>
          <label for="plant-species" class="block text-xs text-neutral-400 mb-1">Вид</label>
          <input
            id="plant-species"
            name="species"
            v-model="form.species"
            type="text"
            placeholder="Lactuca sativa"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
            autocomplete="off"
          />
        </div>

        <div>
          <label for="plant-variety" class="block text-xs text-neutral-400 mb-1">Сорт</label>
          <input
            id="plant-variety"
            name="variety"
            v-model="form.variety"
            type="text"
            placeholder="Айсберг"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
            autocomplete="off"
          />
        </div>

        <div>
          <label for="plant-substrate" class="block text-xs text-neutral-400 mb-1">Субстрат</label>
          <select
            id="plant-substrate"
            name="substrate_type"
            v-model="form.substrate_type"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
          >
            <option value="">Не выбрано</option>
            <option v-for="option in taxonomies.substrate_type" :key="option.id" :value="option.id">
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label for="plant-system" class="block text-xs text-neutral-400 mb-1">Система</label>
          <select
            id="plant-system"
            name="growing_system"
            v-model="form.growing_system"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
          >
            <option value="">Не выбрано</option>
            <option v-for="option in taxonomies.growing_system" :key="option.id" :value="option.id">
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label for="plant-photoperiod" class="block text-xs text-neutral-400 mb-1">Фотопериод</label>
          <select
            id="plant-photoperiod"
            name="photoperiod_preset"
            v-model="form.photoperiod_preset"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
          >
            <option value="">Не выбрано</option>
            <option v-for="option in taxonomies.photoperiod_preset" :key="option.id" :value="option.id">
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label for="plant-seasonality" class="block text-xs text-neutral-400 mb-1">Сезонность</label>
          <select
            id="plant-seasonality"
            name="seasonality"
            v-model="form.seasonality"
            class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
          >
            <option value="">Не выбрано</option>
            <option v-for="option in seasonOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>

        <div class="md:col-span-2">
          <label for="plant-description" class="block text-xs text-neutral-400 mb-1">Описание</label>
          <textarea
            id="plant-description"
            name="description"
            v-model="form.description"
            rows="3"
            placeholder="Описание растения..."
            class="w-full rounded-md border px-2 py-1 text-sm border-neutral-700 bg-neutral-900"
            autocomplete="off"
          ></textarea>
        </div>

        <div class="md:col-span-2">
          <p class="text-sm font-semibold text-neutral-200 mb-2">Диапазоны параметров</p>
          <div class="grid grid-cols-2 gap-3" v-for="metric in rangeMetrics" :key="metric.key">
            <div>
              <label :for="`plant-${metric.key}-min`" class="block text-xs text-neutral-400 mb-1">{{ metric.label }} (мин)</label>
              <input
                :id="`plant-${metric.key}-min`"
                :name="`${metric.key}_min`"
                v-model.number="form.environment_requirements[metric.key].min"
                type="number"
                step="0.1"
                placeholder="Мин"
                class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                autocomplete="off"
              />
            </div>
            <div>
              <label :for="`plant-${metric.key}-max`" class="block text-xs text-neutral-400 mb-1">{{ metric.label }} (макс)</label>
              <input
                :id="`plant-${metric.key}-max`"
                :name="`${metric.key}_max`"
                v-model.number="form.environment_requirements[metric.key].max"
                type="number"
                step="0.1"
                placeholder="Макс"
                class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                autocomplete="off"
              />
            </div>
          </div>
        </div>
      </div>

      <div v-if="errors.general" class="text-sm text-red-400">{{ errors.general }}</div>
    </form>

    <template #footer>
      <Button type="button" @click="onSubmit" :disabled="loading || !form.name.trim()">
        {{ loading ? 'Создание...' : 'Создать' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface EnvironmentRange {
  min?: number | string | null
  max?: number | string | null
}

interface TaxonomyOption {
  id: string
  label: string
}

interface Props {
  show?: boolean
  taxonomies?: Record<string, TaxonomyOption[]>
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  taxonomies: () => ({})
})

const emit = defineEmits<{
  close: []
  created: [plant: any]
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const errors = reactive<Record<string, string>>({})

const taxonomies = computed(() => ({
  substrate_type: props.taxonomies?.substrate_type ?? [],
  growing_system: props.taxonomies?.growing_system ?? [],
  photoperiod_preset: props.taxonomies?.photoperiod_preset ?? [],
}))

const seasonOptions = [
  { value: 'all_year', label: 'Круглый год' },
  { value: 'multi_cycle', label: 'Несколько циклов' },
  { value: 'seasonal', label: 'Сезонное выращивание' },
]

const rangeMetrics = [
  { key: 'temperature', label: 'Температура (°C)' },
  { key: 'humidity', label: 'Влажность (%)' },
  { key: 'ph', label: 'pH' },
  { key: 'ec', label: 'EC (мСм/см)' },
]

const emptyEnvironment = () =>
  rangeMetrics.reduce((acc, metric) => {
    acc[metric.key] = { min: '', max: '' }
    return acc
  }, {} as Record<string, EnvironmentRange>)

const form = reactive({
  name: '',
  species: '',
  variety: '',
  substrate_type: '',
  growing_system: '',
  photoperiod_preset: '',
  seasonality: '',
  description: '',
  environment_requirements: emptyEnvironment(),
})

// Сброс формы при открытии модального окна
watch(() => props.show, (newVal: boolean) => {
  if (newVal) {
    resetForm()
  }
})

function resetForm() {
  form.name = ''
  form.species = ''
  form.variety = ''
  form.substrate_type = ''
  form.growing_system = ''
  form.photoperiod_preset = ''
  form.seasonality = ''
  form.description = ''
  form.environment_requirements = emptyEnvironment()
  Object.keys(errors).forEach(key => delete errors[key])
}

function handleClose() {
  resetForm()
  emit('close')
}

async function onSubmit() {
  if (!form.name || !form.name.trim()) {
    showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.value = true
  errors.name = ''
  errors.general = ''
  
  try {
    // Очищаем пустые значения из environment_requirements
    const cleanedEnv: Record<string, EnvironmentRange> = {}
    Object.keys(form.environment_requirements).forEach(key => {
      const range = form.environment_requirements[key]
      if (range.min !== '' || range.max !== '') {
        cleanedEnv[key] = {
          min: range.min === '' ? null : range.min,
          max: range.max === '' ? null : range.max,
        }
      }
    })
    
    const payload: any = {
      name: form.name.trim(),
      species: form.species.trim() || null,
      variety: form.variety.trim() || null,
      substrate_type: form.substrate_type || null,
      growing_system: form.growing_system || null,
      photoperiod_preset: form.photoperiod_preset || null,
      seasonality: form.seasonality || null,
      description: form.description.trim() || null,
    }
    
    // Добавляем environment_requirements только если есть данные
    if (Object.keys(cleanedEnv).length > 0) {
      payload.environment_requirements = cleanedEnv
    }
    
    const response = await api.post('/plants', payload)
    
    logger.info('Plant created:', response.data)
    showToast('Растение успешно создано', 'success', TOAST_TIMEOUT.NORMAL)
    
    const plant = (response.data as any)?.data || response.data
    emit('created', plant)
    handleClose()
    
    // Обновляем страницу для отображения нового растения
    router.reload({ only: ['plants'] })
  } catch (error: any) {
    logger.error('Failed to create plant:', error)
    
    // Обработка ошибок валидации (422)
    if (error.response?.data?.errors) {
      Object.keys(error.response.data.errors).forEach(key => {
        errors[key] = error.response.data.errors[key][0]
      })
    } else if (error.response?.data?.message) {
      errors.general = error.response.data.message
    }
  } finally {
    loading.value = false
  }
}
</script>

