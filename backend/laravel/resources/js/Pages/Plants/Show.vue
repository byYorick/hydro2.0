<template>
  <AppLayout>
    <Head :title="plant.name" />
    <div class="flex flex-col gap-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="text-lg font-semibold truncate">
            {{ plant.name }}
          </div>
          <div class="text-xs text-[color:var(--text-muted)] mt-1">
            <span v-if="plant.species">{{ plant.species }}</span>
            <span v-if="plant.variety"> · {{ plant.variety }}</span>
            <span
              v-if="plant.description"
              class="block sm:inline sm:ml-1"
            >
              <span
                v-if="plant.species || plant.variety"
                class="hidden sm:inline"
              >·</span>
              {{ plant.description }}
            </span>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Link href="/plants">
            <Button
              size="sm"
              variant="secondary"
            >
              Назад к списку
            </Button>
          </Link>
          <Button
            size="sm"
            variant="outline"
            @click="openEditModal"
          >
            Редактировать
          </Button>
          <Button
            size="sm"
            variant="danger"
            :disabled="deleting"
            @click="deletePlant"
          >
            Удалить
          </Button>
        </div>
      </div>

      <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <!-- Основная информация -->
        <Card class="xl:col-span-2">
          <div class="text-sm font-semibold mb-3">
            Основная информация
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Вид
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.species || '—' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Сорт
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.variety || '—' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Субстрат
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.substrate_type ? taxonomyLabel('substrate_type', plant.substrate_type) : '—' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Система выращивания
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.growing_system ? taxonomyLabel('growing_system', plant.growing_system) : '—' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Фотопериод
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ plant.photoperiod_preset ? taxonomyLabel('photoperiod_preset', plant.photoperiod_preset) : '—' }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] mb-1">
                Сезонность
              </div>
              <div class="text-sm text-[color:var(--text-primary)]">
                {{ seasonalityLabel(plant.seasonality) }}
              </div>
            </div>
          </div>
          <div
            v-if="plant.description"
            class="mt-4"
          >
            <div class="text-xs text-[color:var(--text-muted)] mb-1">
              Описание
            </div>
            <div class="text-sm text-[color:var(--text-muted)] leading-relaxed">
              {{ plant.description }}
            </div>
          </div>
        </Card>

        <!-- Экономика -->
        <Card v-if="plant.profitability?.has_pricing">
          <div class="text-sm font-semibold mb-3">
            Экономика
          </div>
          <div class="space-y-3">
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Себестоимость
              </div>
              <div class="text-lg font-semibold text-[color:var(--text-primary)]">
                {{ formatCurrency(plant.profitability.total_cost, plant.profitability.currency) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Оптовая цена
              </div>
              <div class="text-lg font-semibold text-[color:var(--accent-green)]">
                {{ formatCurrency(plant.profitability.wholesale_price, plant.profitability.currency) }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Маржа: {{ formatCurrency(plant.profitability.margin_wholesale, plant.profitability.currency) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
                Розничная цена
              </div>
              <div class="text-lg font-semibold text-[color:var(--accent-cyan)]">
                {{ formatCurrency(plant.profitability.retail_price, plant.profitability.currency) }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Маржа: {{ formatCurrency(plant.profitability.margin_retail, plant.profitability.currency) }}
              </div>
            </div>
          </div>
        </Card>
      </div>

      <!-- Диапазоны параметров -->
      <Card v-if="hasEnvironment">
        <div class="text-sm font-semibold mb-3">
          Диапазоны параметров
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            v-for="(range, metric) in plant.environment_requirements"
            :key="metric"
          >
            <div class="text-xs text-[color:var(--text-muted)] uppercase tracking-wide mb-1">
              {{ metricLabel(metric) }}
            </div>
            <div class="text-sm text-[color:var(--text-primary)]">
              {{ formatRange(range) }}
            </div>
          </div>
        </div>
      </Card>

      <!-- Собственные фазы роста -->
      <Card v-if="plant.growth_phases && plant.growth_phases.length > 0">
        <div class="text-sm font-semibold mb-3">
          Фазы роста
        </div>
        <div class="space-y-2">
          <div
            v-for="(phase, index) in plant.growth_phases"
            :key="index"
            class="text-sm text-[color:var(--text-muted)] p-2 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="font-medium">
              {{ phase.name || `Фаза ${index + 1}` }}
            </div>
            <div
              v-if="phase.duration_days"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Длительность: {{ phase.duration_days }} {{ phase.duration_days === 1 ? 'день' : 'дней' }}
            </div>
          </div>
        </div>
      </Card>

      <!-- Рецепты выращивания -->
      <Card v-if="plant.recipes && plant.recipes.length > 0">
        <div class="text-sm font-semibold mb-4">
          Рецепты выращивания
        </div>
        <div class="space-y-4">
          <Card
            v-for="recipe in plant.recipes"
            :key="recipe.id"
            class="p-4"
          >
            <div class="flex items-start justify-between mb-4">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <Link
                    :href="`/recipes/${recipe.id}`"
                    class="text-base font-semibold text-[color:var(--accent-cyan)] hover:underline"
                  >
                    {{ recipe.name }}
                  </Link>
                  <Badge
                    v-if="recipe.is_default"
                    size="xs"
                    variant="info"
                  >
                    По умолчанию
                  </Badge>
                </div>
                <div
                  v-if="recipe.description"
                  class="text-sm text-[color:var(--text-muted)] mb-1"
                >
                  {{ recipe.description }}
                </div>
                <div
                  v-if="recipe.season || recipe.site_type"
                  class="text-xs text-[color:var(--text-dim)]"
                >
                  <span v-if="recipe.season">Сезон: {{ recipe.season }}</span>
                  <span
                    v-if="recipe.site_type"
                    class="ml-2"
                  >Тип: {{ recipe.site_type }}</span>
                </div>
              </div>
            </div>
            <div
              v-if="recipe.phases && recipe.phases.length > 0"
              class="mt-3"
            >
              <div class="text-xs text-[color:var(--text-muted)] mb-3">
                Фазы ({{ recipe.phases.length }}):
              </div>
              <div class="space-y-4">
                <Card
                  v-for="phase in recipe.phases"
                  :key="phase.id"
                  class="p-4"
                >
                  <div class="flex items-center justify-between mb-4">
                    <div class="font-semibold text-base text-[color:var(--text-primary)]">
                      {{ phase.phase_index + 1 }}. {{ phase.name }}
                    </div>
                    <div class="text-sm text-[color:var(--text-muted)]">
                      Длительность: {{ formatDuration(phase.duration_hours) }}
                    </div>
                  </div>
                  <div
                    v-if="hasPhaseTargets(phase.targets)"
                    class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
                  >
                    <!-- pH -->
                    <div
                      v-if="hasTargetValue(phase.targets?.ph)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        pH
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatTargetRange(phase.targets?.ph) }}
                      </div>
                    </div>
                    <!-- EC -->
                    <div
                      v-if="hasTargetValue(phase.targets?.ec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        EC (мСм/см)
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatTargetRange(phase.targets?.ec) }}
                      </div>
                    </div>
                    <!-- Температура -->
                    <div
                      v-if="hasTargetValue(phase.targets?.temp_air)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Температура воздуха
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.temp_air }}°C
                      </div>
                    </div>
                    <!-- Влажность -->
                    <div
                      v-if="hasTargetValue(phase.targets?.humidity_air)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Влажность воздуха
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.humidity_air }}%
                      </div>
                    </div>
                    <!-- Свет -->
                    <div
                      v-if="hasTargetValue(phase.targets?.light_hours)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Световой день
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.light_hours }} ч
                      </div>
                    </div>
                    <!-- Интервал полива -->
                    <div
                      v-if="hasTargetValue(phase.targets?.irrigation_interval_sec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Интервал полива
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ formatIrrigationInterval(phase.targets?.irrigation_interval_sec) }}
                      </div>
                    </div>
                    <!-- Длительность полива -->
                    <div
                      v-if="hasTargetValue(phase.targets?.irrigation_duration_sec)"
                      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
                    >
                      <div class="text-xs text-[color:var(--text-muted)] mb-1 uppercase tracking-wide">
                        Длительность полива
                      </div>
                      <div class="text-base font-semibold text-[color:var(--text-primary)]">
                        {{ phase.targets?.irrigation_duration_sec }} сек
                      </div>
                    </div>
                  </div>
                  <div
                    v-else
                    class="text-xs text-[color:var(--text-dim)] text-center py-2"
                  >
                    Параметры не заданы
                  </div>
                </Card>
              </div>
            </div>
            <div
              v-else
              class="text-xs text-[color:var(--text-dim)] mt-2"
            >
              Нет фаз в рецепте
            </div>
          </Card>
        </div>
      </Card>

      <!-- Редактирование в модальном окне -->
      <Modal
        :open="showEditModal"
        title="Редактирование растения"
        size="large"
        @close="closeEditModal"
      >
        <form
          class="space-y-4"
          @submit.prevent="handleSubmit"
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="md:col-span-2">
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
            <div class="md:col-span-2">
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Описание</label>
              <textarea
                v-model="form.description"
                rows="4"
                class="input-field h-auto"
              ></textarea>
            </div>
            <div class="md:col-span-2">
              <p class="text-sm font-semibold text-[color:var(--text-primary)] mb-2">
                Диапазоны
              </p>
              <div
                v-for="metric in rangeMetrics"
                :key="metric.key"
                class="grid grid-cols-2 gap-3"
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
          </div>
        </form>
        <template #footer>
          <Button
            type="button"
            variant="secondary"
            :disabled="form.processing"
            @click="closeEditModal"
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

      <ConfirmModal
        :open="deleteModalOpen"
        title="Удалить растение"
        :message="plant?.name ? `Удалить растение '${plant.name}'?` : 'Удалить растение?'"
        confirm-text="Удалить"
        confirm-variant="danger"
        :loading="deleting"
        @close="deleteModalOpen = false"
        @confirm="confirmDeletePlant"
      />
    </div>
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
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { useToast } from '@/composables/useToast'
import { useSimpleModal } from '@/composables/useModal'
import { usePageProps } from '@/composables/usePageProps'
import {
  formatCurrency,
  formatDuration,
  formatIrrigationInterval,
  formatRange,
  formatTargetRange,
  hasPhaseTargets,
  hasTargetValue,
} from '@/utils/plantDisplay'

interface EnvironmentRange {
  min?: number | string | null
  max?: number | string | null
}

interface RecipePhase {
  id: number
  phase_index: number
  name: string
  duration_hours: number
  targets?: {
    ph?: { min?: number; max?: number } | number | null
    ec?: { min?: number; max?: number } | number | null
    temp_air?: number | null
    humidity_air?: number | null
    light_hours?: number | null
    irrigation_interval_sec?: number | null
    irrigation_duration_sec?: number | null
    [key: string]: any
  }
}

interface PlantRecipe {
  id: number
  name: string
  description?: string
  is_default?: boolean
  season?: string
  site_type?: string
  phases?: RecipePhase[]
  phases_count?: number
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
  growth_phases?: Array<{ name?: string; duration_days?: number }>
  recipes?: PlantRecipe[]
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

interface PageProps {
  plant?: PlantSummary
  taxonomies?: Record<string, TaxonomyOption[]>
  [key: string]: any
}

const { plant: plantProp, taxonomies: taxonomiesProp } = usePageProps<PageProps>(['plant', 'taxonomies'])
const plant = computed(() => (plantProp.value || {}) as PlantSummary)
const taxonomies = computed(() => ({
  substrate_type: (taxonomiesProp.value as any)?.substrate_type ?? [],
  growing_system: (taxonomiesProp.value as any)?.growing_system ?? [],
  photoperiod_preset: (taxonomiesProp.value as any)?.photoperiod_preset ?? [],
  seasonality: (taxonomiesProp.value as any)?.seasonality ?? [],
}))

const { showToast } = useToast()
const { isOpen: showEditModal, open: openEditModal, close: closeEditModal } = useSimpleModal()
const deleting = ref(false)
const deleteModalOpen = ref(false)

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

const hasEnvironment = computed(() => {
  return Boolean(plant.value.environment_requirements && Object.keys(plant.value.environment_requirements).length > 0)
})

function taxonomyLabel(key: string, value?: string | null): string {
  if (!value) return '—'
  return taxonomyIndex.value[key]?.[value] ?? value
}

function seasonalityLabel(value?: string | null): string {
  if (!value) return '—'
  const fallback = seasonOptions.value.find(option => option.id === value)
  return taxonomyIndex.value.seasonality?.[value] ?? fallback?.label ?? value
}

function metricLabel(metric: string): string {
  const metricMap: Record<string, string> = {
    temperature: 'Температура (°C)',
    humidity: 'Влажность (%)',
    ph: 'pH',
    ec: 'EC (мСм/см)',
  }
  return metricMap[metric] || metric
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

watch(() => showEditModal.value, (newVal: boolean) => {
  if (newVal && plant.value) {
    form.reset({
      name: plant.value.name,
      slug: plant.value.slug,
      species: plant.value.species || '',
      variety: plant.value.variety || '',
      substrate_type: plant.value.substrate_type || '',
      growing_system: plant.value.growing_system || '',
      photoperiod_preset: plant.value.photoperiod_preset || '',
      seasonality: plant.value.seasonality || '',
      description: plant.value.description || '',
      environment_requirements: populateEnvironment(plant.value.environment_requirements),
    } as any)
    form.clearErrors()
  }
})

function handleSubmit(): void {
  if (!plant.value?.id) return

  form.put(`/plants/${plant.value.id}`, {
    onSuccess: () => {
      showToast('Растение обновлено', 'success')
      closeEditModal()
    },
    onError: () => showToast('Не удалось обновить растение', 'error'),
  })
}

function deletePlant(): void {
  if (!plant.value?.id) return
  deleteModalOpen.value = true
}

function confirmDeletePlant(): void {
  if (!plant.value?.id) return
  deleting.value = true
  router.delete(`/plants/${plant.value.id}`, {
    onSuccess: () => {
      showToast('Растение удалено', 'success')
      deleteModalOpen.value = false
      router.visit('/plants')
    },
    onError: () => {
      showToast('Ошибка при удалении растения', 'error')
      deleting.value = false
    },
  })
}
</script>
