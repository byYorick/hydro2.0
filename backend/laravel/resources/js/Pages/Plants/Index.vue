<template>
  <AppLayout>
    <Head title="Растения" />
    <div class="space-y-4">
      <section class="ui-hero p-5 space-y-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
              агросправочник
            </p>
            <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-1">
              Растения
            </h1>
            <p class="text-sm text-[color:var(--text-muted)]">
              Управление культурами и агропрофилями для зон и рецептов.
            </p>
          </div>
          <Button
            v-if="canConfigurePlants"
            size="sm"
            variant="primary"
            @click="openCreateModal"
          >
            Новое растение
          </Button>
        </div>
        <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-4">
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Растений
            </div>
            <div class="ui-kpi-value">
              {{ totalPlants }}
            </div>
            <div class="ui-kpi-hint">
              Профилей в базе
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              С системой
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
              {{ plantsWithGrowingSystem }}
            </div>
            <div class="ui-kpi-hint">
              Выбрана технология выращивания
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              С фотопериодом
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-green)]">
              {{ plantsWithPhotoperiod }}
            </div>
            <div class="ui-kpi-hint">
              Профиль освещения задан
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Диапазоны заполнены
            </div>
            <div class="ui-kpi-value">
              {{ plantsWithEnvironmentRanges }}
            </div>
            <div class="ui-kpi-hint">
              Есть рабочие пределы pH/EC/климата
            </div>
          </div>
        </div>
      </section>
      <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[720px] flex flex-col">
        <div class="overflow-auto flex-1">
          <table class="w-full border-collapse">
            <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] text-sm sticky top-0 z-10">
              <tr>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Название
                </th>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Вид / Сорт
                </th>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Субстрат
                </th>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Система
                </th>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Фотопериод
                </th>
                <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                  Описание
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(plant, index) in paginatedPlantsData"
                :key="plant.id"
                :class="[
                  index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]',
                  selectedPlantId === plant.id ? 'bg-[color:var(--badge-info-bg)] border-[color:var(--badge-info-border)]' : ''
                ]"
                class="text-sm border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)] transition-colors"
              >
                <td class="px-3 py-2">
                  <Link
                    :href="`/plants/${plant.id}`"
                    class="font-semibold text-[color:var(--accent-cyan)] hover:underline"
                  >
                    {{ plant.name }}
                  </Link>
                </td>
                <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                  <div>
                    <span v-if="plant.species">{{ plant.species }}</span>
                    <span v-if="plant.variety"> · {{ plant.variety }}</span>
                    <span v-if="!plant.species && !plant.variety">—</span>
                  </div>
                </td>
                <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                  <span v-if="plant.substrate_type">{{ taxonomyLabel('substrate_type', plant.substrate_type) }}</span>
                  <span v-else>—</span>
                </td>
                <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                  <span v-if="plant.growing_system">{{ taxonomyLabel('growing_system', plant.growing_system) }}</span>
                  <span v-else>—</span>
                </td>
                <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                  <span v-if="plant.photoperiod_preset">{{ taxonomyLabel('photoperiod_preset', plant.photoperiod_preset) }}</span>
                  <span v-else>—</span>
                </td>
                <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                  <span
                    v-if="plant.description"
                    class="truncate block max-w-xs"
                  >{{ plant.description }}</span>
                  <span v-else>—</span>
                </td>
              </tr>
              <tr v-if="paginatedPlants.length === 0">
                <td
                  colspan="6"
                  class="px-3 py-6 text-sm text-[color:var(--text-dim)] text-center"
                >
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
    <Modal
      v-if="selectedPlant"
      :open="isEditing"
      title="Редактирование растения"
      size="large"
      @close="resetForm"
    >
      <form
        class="space-y-4"
        @submit.prevent="handleSubmit"
      >
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название</label>
          <input
            v-model="form.name"
            type="text"
            class="input-field"
          />
          <p
            v-if="form.errors.name"
            class="text-xs text-[color:var(--badge-danger-text)] mt-1"
          >
            {{ form.errors.name }}
          </p>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Вид</label>
            <input
              v-model="form.species"
              type="text"
              class="input-field"
            />
          </div>
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Сорт</label>
            <input
              v-model="form.variety"
              type="text"
              class="input-field"
            />
          </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Субстрат</label>
            <select
              v-model="form.substrate_type"
              class="input-select"
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
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Система</label>
            <select
              v-model="form.growing_system"
              class="input-select"
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
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Фотопериод</label>
            <select
              v-model="form.photoperiod_preset"
              class="input-select"
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
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Сезонность</label>
            <select
              v-model="form.seasonality"
              class="input-select"
            >
              <option value="">
                Не выбрано
              </option>
              <option
                v-for="option in seasonOptions"
                :key="option.id"
                :value="option.id"
              >
                {{ option.label }}
              </option>
            </select>
          </div>
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Описание</label>
          <textarea
            v-model="form.description"
            rows="4"
            class="input-field h-auto"
          ></textarea>
        </div>
        <div class="space-y-2">
          <p class="text-sm font-semibold text-[color:var(--text-primary)]">
            Диапазоны
          </p>
          <div
            v-for="metric in rangeMetrics"
            :key="metric.key"
            class="grid grid-cols-2 gap-2"
          >
            <label class="text-xs text-[color:var(--text-muted)] col-span-2">{{ metric.label }}</label>
            <input
              v-model="form.environment_requirements[metric.key].min"
              type="number"
              step="0.1"
              class="input-field h-8 text-xs"
              placeholder="Мин"
            />
            <input
              v-model="form.environment_requirements[metric.key].max"
              type="number"
              step="0.1"
              class="input-field h-8 text-xs"
              placeholder="Макс"
            />
          </div>
        </div>
      </form>
      <template #footer>
        <Button
          type="button"
          variant="secondary"
          :disabled="form.processing"
          @click="resetForm"
        >
          Отмена
        </Button>
        <Button
          type="button"
          :disabled="form.processing"
          @click="handleSubmit"
        >
          Сохранить
        </Button>
      </template>
    </Modal>

    <!-- Модальное окно создания растения -->
    <PlantCreateModal
      :show="showCreateModal"
      :taxonomies="props.taxonomies"
      @close="closeCreateModal"
      @created="onPlantCreated"
    />

    <ConfirmModal
      :open="deleteModal.open"
      title="Удалить растение"
      :message="deleteModal.plant ? `Удалить растение '${deleteModal.plant.name}'?` : 'Удалить растение?'"
      confirm-text="Удалить"
      confirm-variant="danger"
      :loading="Boolean(deletingId)"
      @close="deleteModal = { open: false, plant: null }"
      @confirm="confirmDeletePlant"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { Head, useForm, router, Link, usePage } from '@inertiajs/vue3'
import { computed, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import Pagination from '@/Components/Pagination.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
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
const page = usePage<{ auth?: { user?: { role?: string } } }>()
const canConfigurePlants = computed(() => {
  const role = page.props.auth?.user?.role ?? 'viewer'
  return role === 'agronomist' || role === 'admin'
})
const totalPlants = computed(() => props.plants.length)
const plantsWithGrowingSystem = computed(() => props.plants.filter((plant) => Boolean(plant.growing_system)).length)
const plantsWithPhotoperiod = computed(() => props.plants.filter((plant) => Boolean(plant.photoperiod_preset)).length)
const plantsWithEnvironmentRanges = computed(() => {
  const metricKeys = ['temperature', 'humidity', 'ph', 'ec']
  return props.plants.filter((plant) => {
    const requirements = plant.environment_requirements
    if (!requirements) return false

    return metricKeys.some((metricKey) => {
      const range = requirements[metricKey]
      if (!range) return false
      const hasMin = range.min !== null && range.min !== undefined && range.min !== ''
      const hasMax = range.max !== null && range.max !== undefined && range.max !== ''
      return hasMin || hasMax
    })
  }).length
})
const selectedPlantId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const deleteModal = ref<{ open: boolean; plant: PlantSummary | null }>({ open: false, plant: null })
const currentPage = ref<number>(1)
const perPage = ref<number>(25)

function clampCurrentPage(total: number): number {
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  return validPage
}

watch([() => props.plants.length, perPage], () => {
  if (props.plants.length > 0) {
    clampCurrentPage(props.plants.length)
  } else {
    currentPage.value = 1
  }
})

const paginatedPlants = computed(() => {
  const total = props.plants.length
  if (total === 0) return []
  
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return props.plants.slice(start, end)
})

const paginatedPlantsData = computed(() => paginatedPlants.value)
const selectedPlant = computed(() => {
  // Ищем в полном списке, а не только в пагинированных
  return props.plants.find(plant => plant.id === selectedPlantId.value) ?? null
})

const taxonomies = computed(() => ({
  substrate_type: props.taxonomies?.substrate_type ?? [],
  growing_system: props.taxonomies?.growing_system ?? [],
  photoperiod_preset: props.taxonomies?.photoperiod_preset ?? [],
  seasonality: props.taxonomies?.seasonality ?? [],
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

const defaultSeasonality = [
  { id: 'all_year', label: 'Круглый год' },
  { id: 'multi_cycle', label: 'Несколько циклов' },
  { id: 'seasonal', label: 'Сезонное выращивание' },
]
const seasonOptions = computed(() => (
  (taxonomies.value.seasonality && taxonomies.value.seasonality.length > 0)
    ? taxonomies.value.seasonality
    : defaultSeasonality
))

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

function onPlantCreated(_plant: any): void {
  showToast('Растение успешно создано', 'success')
  // Страница уже обновится через router.reload в модальном окне
}


function confirmDeletePlant(): void {
  const plant = deleteModal.value.plant
  if (!plant) return
  deletingId.value = plant.id
  router.delete(`/plants/${plant.id}`, {
    onSuccess: () => showToast('Растение удалено', 'success'),
    onError: () => showToast('Ошибка при удалении растения', 'error'),
    onFinish: () => {
      deletingId.value = null
      if (selectedPlantId.value === plant.id) {
        resetForm()
      }
      deleteModal.value = { open: false, plant: null }
    },
  })
}






watch(selectedPlantId, () => {
  priceForm.clearErrors()
})
</script>

<style scoped>
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
