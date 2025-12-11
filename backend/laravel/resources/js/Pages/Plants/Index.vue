<template>
  <AppLayout>
    <Head title="Растения" />
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-lg font-semibold text-neutral-100">Растения</h1>
          <p class="text-sm text-neutral-400">Управление культурами и их агропрофилями</p>
        </div>
        <Button size="sm" variant="primary" @click="openCreateModal">
          Новое растение
        </Button>
      </div>
      <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
        <div class="overflow-auto flex-1">
          <table class="w-full border-collapse">
              <thead class="bg-neutral-900 text-neutral-300 text-sm sticky top-0 z-10">
                <tr>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Название</th>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Вид / Сорт</th>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Субстрат</th>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Система</th>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Фотопериод</th>
                  <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Описание</th>
                </tr>
              </thead>
            <tbody>
              <tr
                v-for="(plant, index) in plants"
                :key="plant.id"
                :class="[
                  index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925',
                  selectedPlantId === plant.id ? 'bg-sky-950/30 border-sky-600' : ''
                ]"
                class="text-sm border-b border-neutral-900 hover:bg-neutral-900 transition-colors"
              >
                  <td class="px-3 py-2">
                    <Link :href="`/plants/${plant.id}`" class="font-semibold text-sky-400 hover:underline">{{ plant.name }}</Link>
                  </td>
                <td class="px-3 py-2 text-xs text-neutral-400">
                  <div>
                    <span v-if="plant.species">{{ plant.species }}</span>
                    <span v-if="plant.variety"> · {{ plant.variety }}</span>
                    <span v-if="!plant.species && !plant.variety">—</span>
                  </div>
                </td>
                <td class="px-3 py-2 text-xs text-neutral-400">
                  <span v-if="plant.substrate_type">{{ taxonomyLabel('substrate_type', plant.substrate_type) }}</span>
                  <span v-else>—</span>
                </td>
                <td class="px-3 py-2 text-xs text-neutral-400">
                  <span v-if="plant.growing_system">{{ taxonomyLabel('growing_system', plant.growing_system) }}</span>
                  <span v-else>—</span>
                </td>
                <td class="px-3 py-2 text-xs text-neutral-400">
                  <span v-if="plant.photoperiod_preset">{{ taxonomyLabel('photoperiod_preset', plant.photoperiod_preset) }}</span>
                  <span v-else>—</span>
                </td>
                  <td class="px-3 py-2 text-xs text-neutral-400">
                    <span v-if="plant.description" class="truncate block max-w-xs">{{ plant.description }}</span>
                    <span v-else>—</span>
                  </td>
              </tr>
                <tr v-if="paginatedPlants.length === 0">
                  <td colspan="6" class="px-3 py-6 text-sm text-neutral-400 text-center">
                    {{ props.plants.length === 0 ? 'Растения ещё не добавлены — создайте профиль, чтобы связать его с зонами и рецептами.' : 'Нет растений на текущей странице' }}
                  </td>
                </tr>
            </tbody>
          </table>
        </div>
        <Pagination
          v-model:current-page="currentPage"
          v-model:per-page="perPage"
          :total="props.plants.length"
        />
      </div>
    </div>
    
    <!-- Форма редактирования в модальном окне -->
    <Modal :open="isEditing" title="Редактирование растения" @close="resetForm" size="large" v-if="selectedPlant">
      <form @submit.prevent="handleSubmit" class="space-y-4">
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
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="resetForm" :disabled="form.processing">
          Отмена
        </Button>
        <Button type="button" @click="handleSubmit" :disabled="form.processing">Сохранить</Button>
      </template>
    </Modal>

    <!-- Модальное окно создания растения -->
    <PlantCreateModal
      :show="showCreateModal"
      :taxonomies="props.taxonomies"
      @close="closeCreateModal"
      @created="onPlantCreated"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { Head, useForm, router, Link } from '@inertiajs/vue3'
import { computed, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import Pagination from '@/Components/Pagination.vue'
import { useToast } from '@/composables/useToast'
import { useSimpleModal } from '@/composables/useModal'

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
const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useSimpleModal()
const selectedPlantId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const currentPage = ref<number>(1)
const perPage = ref<number>(25)

const paginatedPlants = computed(() => {
  const total = props.plants.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return props.plants.slice(start, end)
})

const plants = computed(() => paginatedPlants.value)
const selectedPlant = computed(() => {
  // Ищем в полном списке, а не только в пагинированных
  return props.plants.find(plant => plant.id === selectedPlantId.value) ?? null
})
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
  if (!isEditing.value || !selectedPlantId.value) {
    showToast('Выберите растение для редактирования', 'warning')
    return
  }
  
  form.put(`/plants/${selectedPlantId.value}`, {
    onSuccess: () => {
      showToast('Растение обновлено', 'success')
      form.clearErrors()
    },
    onError: () => showToast('Не удалось обновить растение', 'error'),
  })
}

function onPlantCreated(plant: any): void {
  showToast('Растение успешно создано', 'success')
  // Страница уже обновится через router.reload в модальном окне
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

table {
  table-layout: auto;
}

th, td {
  white-space: nowrap;
}

th:first-child,
td:first-child {
  white-space: normal;
  min-width: 150px;
  max-width: 200px;
}

th:nth-child(2),
td:nth-child(2) {
  white-space: normal;
  min-width: 150px;
  max-width: 200px;
}

th:nth-child(3),
td:nth-child(3),
th:nth-child(4),
td:nth-child(4),
th:nth-child(5),
td:nth-child(5) {
  min-width: 120px;
}

th:nth-child(6),
td:nth-child(6) {
  white-space: normal;
  min-width: 200px;
  max-width: 300px;
}
</style>

