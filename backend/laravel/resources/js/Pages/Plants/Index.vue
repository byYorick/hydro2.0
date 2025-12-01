<template>
  <AppLayout>
    <Head title="Растения" />
    <div class="flex flex-col xl:flex-row gap-4">
      <div class="xl:w-2/3 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-lg font-semibold text-neutral-100">Растения</h1>
            <p class="text-sm text-neutral-400">Управление культурами и их агропрофилями</p>
          </div>
          <Button size="sm" variant="secondary" @click="resetForm" v-if="isEditing">
            Новый профиль
          </Button>
        </div>
        <Card v-if="plants.length === 0" class="border-dashed border-neutral-700 text-sm text-neutral-400">
          Растения ещё не добавлены — создайте профиль, чтобы связать его с зонами и рецептами.
        </Card>
        <Card
          v-for="plant in plants"
          :key="plant.id"
          class="transition-all duration-200"
          :class="[
            selectedPlantId === plant.id ? 'border-sky-600 shadow-lg shadow-sky-900/30' : 'hover:border-neutral-700'
          ]"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-2">
                <div class="text-base font-semibold text-neutral-100">{{ plant.name }}</div>
                <Badge v-if="plant.substrate_type" size="xs" variant="neutral">
                  {{ taxonomyLabel('substrate_type', plant.substrate_type) }}
                </Badge>
                <Badge v-if="plant.growing_system" size="xs" variant="info">
                  {{ taxonomyLabel('growing_system', plant.growing_system) }}
                </Badge>
              </div>
              <div class="text-xs text-neutral-400 mt-1">
                <span v-if="plant.species">{{ plant.species }}</span>
                <span v-if="plant.variety">· {{ plant.variety }}</span>
                <span v-if="plant.photoperiod_preset">· {{ taxonomyLabel('photoperiod_preset', plant.photoperiod_preset) }}</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <Button size="xs" variant="outline" @click="startEdit(plant)">Редактировать</Button>
              <Button size="xs" variant="danger" @click="deletePlant(plant)" :disabled="deletingId === plant.id">Удалить</Button>
            </div>
          </div>
          <p v-if="plant.description" class="text-sm text-neutral-300 mt-3 leading-relaxed">
            {{ plant.description }}
          </p>
          <div v-if="hasEnvironment(plant)" class="mt-3 text-xs text-neutral-400 space-y-1">
            <div v-for="(range, metric) in plant.environment_requirements" :key="metric" class="flex items-center gap-2">
              <span class="uppercase tracking-wide text-neutral-500">{{ metric }}:</span>
              <span>{{ formatRange(range) }}</span>
            </div>
          </div>
        </Card>
      </div>
      <div class="xl:w-1/3">
        <Card>
          <div class="flex items-center justify-between mb-3">
            <div>
              <h2 class="text-base font-semibold text-neutral-100">
                {{ isEditing ? 'Редактирование растения' : 'Новое растение' }}
              </h2>
              <p class="text-xs text-neutral-400">
                {{ isEditing ? 'Обновите данные профиля растения' : 'Создайте профиль для назначения зонам и рецептам' }}
              </p>
            </div>
          </div>
          <form @submit.prevent="handleSubmit" class="space-y-3">
            <div>
              <label class="form-label">Название</label>
              <input v-model="form.name" type="text" class="form-input" />
              <p v-if="form.errors.name" class="form-error">{{ form.errors.name }}</p>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="form-label">Вид</label>
                <input v-model="form.species" type="text" class="form-input" />
              </div>
              <div>
                <label class="form-label">Сорт</label>
                <input v-model="form.variety" type="text" class="form-input" />
              </div>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="form-label">Субстрат</label>
                <select v-model="form.substrate_type" class="form-input">
                  <option value="">Не выбрано</option>
                  <option v-for="option in taxonomies.substrate_type" :key="option.id" :value="option.id">
                    {{ option.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="form-label">Система</label>
                <select v-model="form.growing_system" class="form-input">
                  <option value="">Не выбрано</option>
                  <option v-for="option in taxonomies.growing_system" :key="option.id" :value="option.id">
                    {{ option.label }}
                  </option>
                </select>
              </div>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="form-label">Фотопериод</label>
                <select v-model="form.photoperiod_preset" class="form-input">
                  <option value="">Не выбрано</option>
                  <option v-for="option in taxonomies.photoperiod_preset" :key="option.id" :value="option.id">
                    {{ option.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="form-label">Сезонность</label>
                <select v-model="form.seasonality" class="form-input">
                  <option value="">Не выбрано</option>
                  <option v-for="option in seasonOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
            </div>
            <div>
              <label class="form-label">Описание</label>
              <textarea v-model="form.description" rows="4" class="form-input"></textarea>
            </div>
            <div class="space-y-2">
              <p class="text-sm font-semibold text-neutral-200">Диапазоны</p>
              <div class="grid grid-cols-2 gap-2" v-for="metric in rangeMetrics" :key="metric.key">
                <label class="text-xs text-neutral-400 col-span-2">{{ metric.label }}</label>
                <input
                  v-model="form.environment_requirements[metric.key].min"
                  type="number"
                  step="0.1"
                  class="form-input text-xs"
                  placeholder="Мин"
                />
                <input
                  v-model="form.environment_requirements[metric.key].max"
                  type="number"
                  step="0.1"
                  class="form-input text-xs"
                  placeholder="Макс"
                />
              </div>
            </div>
            <div class="flex items-center gap-2 pt-2">
              <Button type="submit" :disabled="form.processing">
                {{ isEditing ? 'Сохранить' : 'Создать' }}
              </Button>
              <Button type="button" variant="secondary" @click="resetForm" :disabled="form.processing">
                Сбросить
              </Button>
            </div>
          </form>
        </Card>
        <Card class="mt-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h2 class="text-base font-semibold text-neutral-100">Экономика</h2>
              <p class="text-xs text-neutral-400">Маржинальность по выбранному растению</p>
            </div>
          </div>
          <div v-if="currentProfitability?.has_pricing" class="grid grid-cols-2 gap-3">
            <div>
              <p class="text-xs text-neutral-400 uppercase tracking-wide">Себестоимость</p>
              <p class="text-lg font-semibold text-neutral-100">
                {{ formatCurrency(currentProfitability.total_cost, currentProfitability.currency) }}
              </p>
            </div>
            <div>
              <p class="text-xs text-neutral-400 uppercase tracking-wide">Опт</p>
              <p class="text-lg font-semibold text-emerald-400">
                {{ formatCurrency(currentProfitability.wholesale_price, currentProfitability.currency) }}
              </p>
              <p class="text-xs text-neutral-500">Маржа: {{ formatCurrency(currentProfitability.margin_wholesale, currentProfitability.currency) }}</p>
            </div>
            <div>
              <p class="text-xs text-neutral-400 uppercase tracking-wide">Розница</p>
              <p class="text-lg font-semibold text-sky-400">
                {{ formatCurrency(currentProfitability.retail_price, currentProfitability.currency) }}
              </p>
              <p class="text-xs text-neutral-500">Маржа: {{ formatCurrency(currentProfitability.margin_retail, currentProfitability.currency) }}</p>
            </div>
          </div>
          <div v-else class="text-sm text-neutral-400">
            Нет данных по ценам. Добавьте ценовую версию, чтобы увидеть маржинальность.
          </div>
        </Card>
        <Card class="mt-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h2 class="text-base font-semibold text-neutral-100">Новая ценовая версия</h2>
              <p class="text-xs text-neutral-400">Сохраняется к выбранному растению</p>
            </div>
          </div>
          <div v-if="!canEditPricing" class="text-xs text-neutral-500 mb-3">
            Выберите растение, чтобы добавить ценовую версию.
          </div>
          <form @submit.prevent="handlePriceSubmit" class="space-y-3">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="form-label">Дата начала</label>
                <input type="date" v-model="priceForm.effective_from" class="form-input" :disabled="!canEditPricing" />
              </div>
              <div>
                <label class="form-label">Валюта</label>
                <input v-model="priceForm.currency" class="form-input" :disabled="!canEditPricing" />
              </div>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div v-for="field in costFields" :key="field.key">
                <label class="form-label">{{ field.label }}</label>
                <input
                  type="number"
                  step="0.01"
                  v-model="priceForm[field.key]"
                  class="form-input"
                  :disabled="!canEditPricing"
                />
                <p v-if="priceForm.errors[field.key]" class="form-error">{{ priceForm.errors[field.key] }}</p>
              </div>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="form-label">Оптовая цена</label>
                <input
                  type="number"
                  step="0.01"
                  v-model="priceForm.wholesale_price"
                  class="form-input"
                  :disabled="!canEditPricing"
                />
                <p v-if="priceForm.errors.wholesale_price" class="form-error">{{ priceForm.errors.wholesale_price }}</p>
              </div>
              <div>
                <label class="form-label">Розничная цена</label>
                <input
                  type="number"
                  step="0.01"
                  v-model="priceForm.retail_price"
                  class="form-input"
                  :disabled="!canEditPricing"
                />
                <p v-if="priceForm.errors.retail_price" class="form-error">{{ priceForm.errors.retail_price }}</p>
              </div>
            </div>
            <div>
              <label class="form-label">Источник данных</label>
              <input v-model="priceForm.source" class="form-input" :disabled="!canEditPricing" />
            </div>
            <div class="flex items-center gap-2">
              <Button type="submit" :disabled="!canEditPricing || priceForm.processing">
                Сохранить цены
              </Button>
              <Button type="button" variant="secondary" @click="resetPriceForm" :disabled="priceForm.processing">
                Очистить
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { Head, useForm, router } from '@inertiajs/vue3'
import { computed, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useToast } from '@/composables/useToast'

interface EnvironmentRange {
  min?: number | string | null
  max?: number | string | null
}

interface PlantSummary {
  id: number
  slug: string
  name: string
  species?: string | null
  variety?: string | null
  substrate_type?: string | null
  growing_system?: string | null
  photoperiod_preset?: string | null
  seasonality?: string | null
  description?: string | null
  environment_requirements?: Record<string, EnvironmentRange> | null
  created_at?: string
  profitability?: ProfitabilitySnapshot | null
}

interface ProfitabilitySnapshot {
  plant_id: number
  currency: string
  total_cost: number | null
  wholesale_price: number | null
  retail_price: number | null
  margin_wholesale: number | null
  margin_retail: number | null
  has_pricing: boolean
}

interface TaxonomyOption {
  id: string
  label: string
}

interface Props {
  plants: PlantSummary[]
  taxonomies: Record<string, TaxonomyOption[]>
}

const props = defineProps<Props>()
const { showToast } = useToast()
const selectedPlantId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const plants = computed(() => props.plants)
const selectedPlant = computed(() => plants.value.find(plant => plant.id === selectedPlantId.value) ?? null)
const currentProfitability = computed(() => selectedPlant.value?.profitability ?? null)
const canEditPricing = computed(() => selectedPlantId.value !== null)

const taxonomies = computed(() => ({
  substrate_type: props.taxonomies?.substrate_type ?? [],
  growing_system: props.taxonomies?.growing_system ?? [],
  photoperiod_preset: props.taxonomies?.photoperiod_preset ?? [],
}))

const taxonomyIndex = computed(() => {
  const map: Record<string, Record<string, string>> = {}
  Object.entries(taxonomies.value).forEach(([key, options]) => {
    map[key] = options.reduce((acc, option) => {
      acc[option.id] = option.label
      return acc
    }, {} as Record<string, string>)
  })
  return map
})

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

const costFields = [
  { key: 'seedling_cost', label: 'Посадочный материал' },
  { key: 'substrate_cost', label: 'Субстрат' },
  { key: 'nutrient_cost', label: 'Питательные растворы' },
  { key: 'labor_cost', label: 'Труд' },
  { key: 'protection_cost', label: 'Защита' },
  { key: 'logistics_cost', label: 'Логистика' },
  { key: 'other_cost', label: 'Прочее' },
]

const emptyEnvironment = () =>
  rangeMetrics.reduce((acc, metric) => {
    acc[metric.key] = { min: '', max: '' }
    return acc
  }, {} as Record<string, EnvironmentRange>)

const form = useForm({
  name: '',
  slug: '',
  species: '',
  variety: '',
  substrate_type: '',
  growing_system: '',
  photoperiod_preset: '',
  seasonality: '',
  description: '',
  environment_requirements: emptyEnvironment(),
})

const priceForm = useForm({
  effective_from: '',
  currency: 'RUB',
  seedling_cost: '',
  substrate_cost: '',
  nutrient_cost: '',
  labor_cost: '',
  protection_cost: '',
  logistics_cost: '',
  other_cost: '',
  wholesale_price: '',
  retail_price: '',
  source: '',
})

const isEditing = computed(() => selectedPlantId.value !== null)

function taxonomyLabel(key: string, value?: string | null): string {
  if (!value) return '—'
  return taxonomyIndex.value[key]?.[value] ?? value
}

function resetForm(): void {
  selectedPlantId.value = null
  form.reset()
  form.environment_requirements = emptyEnvironment()
  form.clearErrors()
}

function startEdit(plant: PlantSummary): void {
  selectedPlantId.value = plant.id
  form.reset({
    name: plant.name,
    slug: plant.slug,
    species: plant.species || '',
    variety: plant.variety || '',
    substrate_type: plant.substrate_type || '',
    growing_system: plant.growing_system || '',
    photoperiod_preset: plant.photoperiod_preset || '',
    seasonality: plant.seasonality || '',
    description: plant.description || '',
    environment_requirements: populateEnvironment(plant.environment_requirements),
  })
  form.clearErrors()
}

function populateEnvironment(env?: Record<string, EnvironmentRange> | null): Record<string, EnvironmentRange> {
  const template = emptyEnvironment()
  if (!env) {
    return template
  }

  Object.keys(template).forEach((key) => {
    template[key] = {
      min: env[key]?.min ?? '',
      max: env[key]?.max ?? '',
    }
  })

  return template
}

function handleSubmit(): void {
  const payload = form.data()
  if (isEditing.value && selectedPlantId.value) {
    form.put(`/plants/${selectedPlantId.value}`, {
      onSuccess: () => {
        showToast('Растение обновлено', 'success')
        form.clearErrors()
      },
      onError: () => showToast('Не удалось обновить растение', 'error'),
    })
  } else {
    form.post('/plants', {
      onSuccess: () => {
        showToast('Растение создано', 'success')
        resetForm()
      },
      onError: () => showToast('Не удалось создать растение', 'error'),
    })
  }
}

function deletePlant(plant: PlantSummary): void {
  if (!confirm(`Удалить растение "${plant.name}"?`)) {
    return
  }
  deletingId.value = plant.id
  router.delete(`/plants/${plant.id}`, {
    onSuccess: () => showToast('Растение удалено', 'success'),
    onError: () => showToast('Ошибка при удалении растения', 'error'),
    onFinish: () => {
      deletingId.value = null
      if (selectedPlantId.value === plant.id) {
        resetForm()
      }
    },
  })
}

function hasEnvironment(plant: PlantSummary): boolean {
  return Boolean(plant.environment_requirements && Object.keys(plant.environment_requirements).length > 0)
}

function formatRange(range: EnvironmentRange | undefined): string {
  if (!range) return '—'
  const min = range.min ?? ''
  const max = range.max ?? ''
  if (min === '' && max === '') return '—'
  if (min !== '' && max !== '') return `${min} – ${max}`
  return min !== '' ? `от ${min}` : `до ${max}`
}

function formatCurrency(value: number | string | null | undefined, currency = 'RUB'): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) {
    return '—'
  }

  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function handlePriceSubmit(): void {
  if (!selectedPlantId.value) {
    showToast('Выберите растение для добавления цен', 'warning')
    return
  }

  priceForm.post(`/plants/${selectedPlantId.value}/prices`, {
    onSuccess: () => {
      showToast('Ценовая версия сохранена', 'success')
      resetPriceForm()
    },
    onError: () => showToast('Не удалось сохранить ценовую версию', 'error'),
  })
}

function resetPriceForm(): void {
  priceForm.reset()
  priceForm.currency = 'RUB'
  priceForm.clearErrors()
}

watch(selectedPlantId, () => {
  priceForm.clearErrors()
})
</script>

<style scoped>
.form-label {
  @apply text-xs text-neutral-400 block mb-1;
}
.form-input {
  @apply w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none;
}
.form-error {
  @apply text-xs text-red-400 mt-1;
}
</style>

