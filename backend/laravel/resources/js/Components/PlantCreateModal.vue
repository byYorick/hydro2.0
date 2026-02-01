<template>
  <Modal
    :open="show"
    title="Создать растение"
    size="large"
    @close="handleClose"
  >
    <form
      class="space-y-4"
      @submit.prevent="onSubmit"
    >
      <div class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
        <span>Шаг {{ currentStep }} из 2: {{ stepTitle }}</span>
        <div class="flex items-center gap-1">
          <span
            class="h-2 w-2 rounded-full"
            :class="currentStep >= 1 ? 'bg-[color:var(--accent-primary)]' : 'bg-[color:var(--border-muted)]'"
          ></span>
          <span
            class="h-2 w-2 rounded-full"
            :class="currentStep >= 2 ? 'bg-[color:var(--accent-primary)]' : 'bg-[color:var(--border-muted)]'"
          ></span>
        </div>
      </div>

      <div
        v-if="currentStep === 1"
        class="grid grid-cols-1 md:grid-cols-2 gap-4"
      >
        <div class="md:col-span-2">
          <label
            for="plant-name"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >
            Название <span class="text-[color:var(--accent-red)]">*</span>
          </label>
          <input
            id="plant-name"
            v-model="form.name"
            name="name"
            type="text"
            required
            placeholder="Салат Айсберг"
            class="input-field h-9 w-full"
            :class="errors.name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            autocomplete="off"
          />
          <div
            v-if="errors.name"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.name }}
          </div>
        </div>

        <div>
          <label
            for="plant-species"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Вид</label>
          <input
            id="plant-species"
            v-model="form.species"
            name="species"
            type="text"
            placeholder="Lactuca sativa"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label
            for="plant-variety"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Сорт</label>
          <input
            id="plant-variety"
            v-model="form.variety"
            name="variety"
            type="text"
            placeholder="Айсберг"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label
            for="plant-substrate"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Субстрат</label>
          <select
            id="plant-substrate"
            v-model="form.substrate_type"
            name="substrate_type"
            class="input-select h-9 w-full"
          >
            <option value="">
              Не выбрано
            </option>
            <option
              v-for="option in taxonomies.substrate_type"
              :key="option.id"
              :value="option.id"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label
            for="plant-system"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Система</label>
          <select
            id="plant-system"
            v-model="form.growing_system"
            name="growing_system"
            class="input-select h-9 w-full"
          >
            <option value="">
              Не выбрано
            </option>
            <option
              v-for="option in taxonomies.growing_system"
              :key="option.id"
              :value="option.id"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label
            for="plant-photoperiod"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Фотопериод</label>
          <select
            id="plant-photoperiod"
            v-model="form.photoperiod_preset"
            name="photoperiod_preset"
            class="input-select h-9 w-full"
          >
            <option value="">
              Не выбрано
            </option>
            <option
              v-for="option in taxonomies.photoperiod_preset"
              :key="option.id"
              :value="option.id"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <label
            for="plant-seasonality"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Сезонность</label>
          <select
            id="plant-seasonality"
            v-model="form.seasonality"
            name="seasonality"
            class="input-select h-9 w-full"
          >
            <option value="">
              Не выбрано
            </option>
            <option
              v-for="option in seasonOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <div class="md:col-span-2">
          <label
            for="plant-description"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Описание</label>
          <textarea
            id="plant-description"
            v-model="form.description"
            name="description"
            rows="3"
            placeholder="Описание растения..."
            class="input-field w-full"
            autocomplete="off"
          ></textarea>
        </div>
      </div>

      <div
        v-else
        class="space-y-4"
      >
        <div class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-3 py-2 text-xs text-[color:var(--text-muted)]">
          Растение: <span class="text-[color:var(--text-primary)] font-semibold">{{ form.name }}</span>
        </div>
        <div>
          <label
            for="recipe-name"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >
            Название рецепта <span class="text-[color:var(--accent-red)]">*</span>
          </label>
          <input
            id="recipe-name"
            v-model="form.recipe_name"
            name="recipe_name"
            type="text"
            required
            placeholder="Рецепт для салата"
            class="input-field h-9 w-full"
            :class="errors.recipe_name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            autocomplete="off"
          />
          <div
            v-if="errors.recipe_name"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.recipe_name }}
          </div>
        </div>
        <div>
          <label
            for="recipe-description"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Описание рецепта</label>
          <textarea
            id="recipe-description"
            v-model="form.recipe_description"
            name="recipe_description"
            rows="3"
            placeholder="Краткое описание рецепта..."
            class="input-field w-full"
            autocomplete="off"
          ></textarea>
        </div>
      </div>

      <div
        v-if="errors.general"
        class="text-sm text-[color:var(--accent-red)]"
      >
        {{ errors.general }}
      </div>
    </form>

    <template #footer>
      <Button
        v-if="currentStep === 2 && !createdPlantId"
        type="button"
        variant="secondary"
        :disabled="loading"
        @click="goBack"
      >
        Назад
      </Button>
      <Button
        type="button"
        :disabled="loading || isPrimaryDisabled"
        @click="onSubmit"
      >
        {{ loading ? 'Создание...' : primaryLabel }}
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
const currentStep = ref<number>(1)
const createdPlantId = ref<number | null>(null)
const createdPlantData = ref<any | null>(null)

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

const form = reactive({
  name: '',
  species: '',
  variety: '',
  substrate_type: '',
  growing_system: '',
  photoperiod_preset: '',
  seasonality: '',
  description: '',
  recipe_name: '',
  recipe_description: '',
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
  form.recipe_name = ''
  form.recipe_description = ''
  currentStep.value = 1
  createdPlantId.value = null
  createdPlantData.value = null
  Object.keys(errors).forEach(key => delete errors[key])
}

function handleClose() {
  resetForm()
  emit('close')
}

const stepTitle = computed(() => (currentStep.value === 1 ? 'Данные растения' : 'Рецепт выращивания'))
const primaryLabel = computed(() => {
  if (currentStep.value === 1) {
    return 'Далее'
  }

  return createdPlantId.value ? 'Создать рецепт' : 'Создать'
})
const isPrimaryDisabled = computed(() => {
  if (currentStep.value === 1) {
    return !form.name.trim()
  }

  return !form.recipe_name.trim()
})

function goBack() {
  currentStep.value = 1
  errors.general = ''
  errors.recipe_name = ''
}

async function onSubmit() {
  if (currentStep.value === 1) {
    if (!form.name || !form.name.trim()) {
      showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    currentStep.value = 2
    return
  }

  if (!form.recipe_name || !form.recipe_name.trim()) {
    showToast('Введите название рецепта', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  if (!form.name || !form.name.trim()) {
    showToast('Введите название растения', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.value = true
  errors.name = ''
  errors.recipe_name = ''
  errors.general = ''
  
  try {
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

    if (!createdPlantId.value) {
      try {
        const response = await api.post('/plants', payload)
        const plant = (response.data as any)?.data || response.data
        createdPlantId.value = plant?.id ?? null
        createdPlantData.value = plant
        logger.info('Plant created:', response.data)
      } catch (error: any) {
        logger.error('Failed to create plant:', error)
        if (error.response?.data?.errors) {
          Object.keys(error.response.data.errors).forEach(key => {
            errors[key] = error.response.data.errors[key][0]
          })
        } else if (error.response?.data?.message) {
          errors.general = error.response.data.message
        }
        currentStep.value = 1
        return
      }
    }

    try {
      await api.post('/recipes', {
        name: form.recipe_name.trim(),
        description: form.recipe_description.trim() || null,
        plant_id: createdPlantId.value,
      })
    } catch (error: any) {
      logger.error('Failed to create recipe:', error)
      if (error.response?.data?.errors) {
        Object.keys(error.response.data.errors).forEach(key => {
          if (key === 'name') {
            errors.recipe_name = error.response.data.errors[key][0]
          } else {
            errors[key] = error.response.data.errors[key][0]
          }
        })
      } else if (error.response?.data?.message) {
        errors.general = error.response.data.message
      }
      return
    }

    showToast('Растение и рецепт успешно созданы', 'success', TOAST_TIMEOUT.NORMAL)
    emit('created', createdPlantData.value)
    handleClose()
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
