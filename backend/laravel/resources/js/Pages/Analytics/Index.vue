<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader
        title="Аналитика"
        subtitle="Графики, отчеты и сравнения по выращиванию."
        eyebrow="данные и отчеты"
      />

      <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">
          Сохранённые виды
        </div>
        <FilterBar data-testid="analytics-views-filters">
          <div class="flex items-center gap-2 flex-1 sm:flex-none">
            <label class="text-sm text-[color:var(--text-muted)] shrink-0">Вид:</label>
            <select
              v-model="activeViewId"
              class="input-select flex-1 sm:w-auto sm:min-w-[220px]"
              data-testid="analytics-view-select"
            >
              <option value="">— выбрать —</option>
              <option v-for="view in savedViews" :key="view.id" :value="view.id">
                {{ view.name }}
              </option>
            </select>
          </div>
          <div class="flex items-center gap-2 flex-1 sm:flex-none">
            <label class="text-sm text-[color:var(--text-muted)] shrink-0">Имя:</label>
            <input
              v-model="newViewName"
              placeholder="Название вида"
              class="input-field flex-1 sm:w-60"
              data-testid="analytics-view-name"
            />
          </div>
          <template #actions>
            <Button
              size="sm"
              variant="secondary"
              @click="saveView"
              :disabled="!canSaveView"
              data-testid="analytics-view-save"
            >
              Сохранить
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="deleteView"
              :disabled="!activeViewId"
              data-testid="analytics-view-delete"
            >
              Удалить
            </Button>
          </template>
        </FilterBar>
      </section>

      <section class="space-y-4">
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">
            Агрегаты телеметрии
          </div>
          <FilterBar data-testid="analytics-telemetry-filters">
            <div class="flex items-center gap-2 flex-1 sm:flex-none">
              <label class="text-sm text-[color:var(--text-muted)] shrink-0">Зона:</label>
              <select
                v-model="selectedZoneId"
                class="input-select flex-1 sm:w-auto sm:min-w-[200px]"
                data-testid="analytics-filter-zone"
              >
                <option value="">Выберите зону</option>
                <option v-for="zone in zoneOptions" :key="zone.id" :value="String(zone.id)">
                  {{ zone.name }}
                </option>
              </select>
            </div>
            <div class="flex items-center gap-2 flex-1 sm:flex-none">
              <label class="text-sm text-[color:var(--text-muted)] shrink-0">Метрика:</label>
              <select
                v-model="selectedMetric"
                class="input-select flex-1 sm:w-auto sm:min-w-[160px]"
                data-testid="analytics-filter-metric"
              >
                <option v-for="metric in metricOptions" :key="metric.value" :value="metric.value">
                  {{ metric.label }}
                </option>
              </select>
            </div>
            <div class="flex items-center gap-2 flex-1 sm:flex-none">
              <label class="text-sm text-[color:var(--text-muted)] shrink-0">Период:</label>
              <select
                v-model="selectedPeriod"
                class="input-select flex-1 sm:w-auto sm:min-w-[120px]"
                data-testid="analytics-filter-period"
              >
                <option v-for="period in periodOptions" :key="period.value" :value="period.value">
                  {{ period.label }}
                </option>
              </select>
            </div>
            <div class="flex items-center gap-2 flex-1 sm:flex-none">
              <button
                type="button"
                class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
                :class="showMedian
                  ? 'border-[color:var(--accent-amber)] text-[color:var(--accent-amber)] bg-[color:var(--bg-elevated)]'
                  : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
                @click="showMedian = !showMedian"
                data-testid="analytics-filter-median"
              >
                Median
              </button>
            </div>
            <template #actions>
              <Button
                size="sm"
                variant="outline"
                @click="loadTelemetryAggregates"
                :disabled="telemetryLoading || !selectedZoneId"
                data-testid="analytics-telemetry-refresh"
              >
                {{ telemetryLoading ? 'Загрузка...' : 'Обновить' }}
              </Button>
            </template>
          </FilterBar>
        </div>

        <TelemetryAggregatesChart
          :data="telemetryData"
          :loading="telemetryLoading"
          :error="telemetryError"
          :metric="selectedMetric"
          :period="selectedPeriodLabel"
          :show-median="showMedian"
          test-id="analytics-telemetry-chart"
        />
      </section>

      <section class="space-y-4">
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">
            Эффективность рецептов
          </div>
          <FilterBar data-testid="analytics-recipe-filters">
            <div class="flex items-center gap-2 flex-1 sm:flex-none">
              <label class="text-sm text-[color:var(--text-muted)] shrink-0">Рецепт:</label>
              <select
                v-model="selectedRecipeId"
                class="input-select flex-1 sm:w-auto sm:min-w-[220px]"
                data-testid="analytics-filter-recipe"
              >
                <option value="">Выберите рецепт</option>
                <option v-for="recipe in recipeOptions" :key="recipe.id" :value="String(recipe.id)">
                  {{ recipe.name }}
                </option>
              </select>
            </div>
            <template #actions>
              <Button
                size="sm"
                variant="outline"
                @click="loadRecipeAnalytics"
                :disabled="recipeLoading || !selectedRecipeId"
                data-testid="analytics-recipe-refresh"
              >
                {{ recipeLoading ? 'Загрузка...' : 'Обновить' }}
              </Button>
            </template>
          </FilterBar>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Средняя эффективность</div>
            <div class="text-2xl font-semibold text-[color:var(--accent-cyan)] mt-1">
              {{ formatNumber(recipeStats?.avg_efficiency, 2) }}
            </div>
          </div>
          <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Отклонение pH</div>
            <div class="text-2xl font-semibold text-[color:var(--accent-amber)] mt-1">
              {{ formatNumber(recipeStats?.avg_ph_deviation_overall, 2) }}
            </div>
          </div>
          <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Отклонение EC</div>
            <div class="text-2xl font-semibold text-[color:var(--accent-amber)] mt-1">
              {{ formatNumber(recipeStats?.avg_ec_deviation_overall, 2) }}
            </div>
          </div>
          <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Средняя длительность</div>
            <div class="text-2xl font-semibold text-[color:var(--accent-green)] mt-1">
              {{ formatDuration(recipeStats?.avg_duration_hours) }}
            </div>
          </div>
        </div>

        <DataTableV2
          :columns="recipeColumns"
          :rows="recipeRuns"
          :loading="recipeLoading"
          empty-title="Нет запусков"
          empty-description="Выберите рецепт и дождитесь данных аналитики."
          :virtualize="false"
        >
          <template #cell-zone="{ row }">
            {{ row.zone?.name || (row.zone_id ? `Zone #${row.zone_id}` : '-') }}
          </template>
          <template #cell-start_date="{ row }">
            {{ formatDate(row.start_date) }}
          </template>
          <template #cell-end_date="{ row }">
            {{ formatDate(row.end_date) }}
          </template>
          <template #cell-efficiency_score="{ row }">
            {{ formatNumber(row.efficiency_score, 2) }}
          </template>
          <template #cell-avg_ph_deviation="{ row }">
            {{ formatNumber(row.avg_ph_deviation, 2) }}
          </template>
          <template #cell-avg_ec_deviation="{ row }">
            {{ formatNumber(row.avg_ec_deviation, 2) }}
          </template>
          <template #cell-alerts_count="{ row }">
            {{ formatNumber(row.alerts_count, 0) }}
          </template>
          <template #cell-total_duration_hours="{ row }">
            {{ formatDuration(row.total_duration_hours) }}
          </template>
        </DataTableV2>

        <Pagination
          v-if="recipeTotal"
          v-model:current-page="recipePage"
          v-model:per-page="recipePerPage"
          :total="recipeTotal"
        />
      </section>

      <section class="space-y-4">
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">
            Сравнение рецептов
          </div>
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div class="surface-card border border-[color:var(--border-muted)] rounded-xl p-3">
              <div class="text-sm font-semibold mb-2">Рецепты</div>
              <div class="space-y-2 max-h-[220px] overflow-y-auto">
                <label v-for="recipe in recipeOptions" :key="recipe.id" class="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    class="h-4 w-4 accent-[color:var(--accent-cyan)]"
                    :value="String(recipe.id)"
                    v-model="compareRecipeIds"
                  />
                  <span class="text-[color:var(--text-muted)]">{{ recipe.name }}</span>
                </label>
              </div>
            </div>
            <div class="surface-card border border-[color:var(--border-muted)] rounded-xl p-3 lg:col-span-2">
              <div class="flex items-center justify-between mb-2">
                <div class="text-sm font-semibold">Итоги сравнения</div>
                <Button
                  size="sm"
                  variant="secondary"
                  @click="loadComparison"
                  :disabled="compareRecipeIds.length < 2 || compareLoading"
                >
                  {{ compareLoading ? 'Сравниваем...' : 'Сравнить' }}
                </Button>
              </div>
              <DataTableV2
                :columns="compareColumns"
                :rows="comparisonRows"
                :loading="compareLoading"
                empty-title="Нет данных для сравнения"
                empty-description="Выберите минимум 2 рецепта."
                :virtualize="false"
              >
                <template #cell-recipe_name="{ row }">
                  {{ row.recipe?.name || `Рецепт #${row.recipe_id}` }}
                </template>
                <template #cell-avg_efficiency="{ row }">
                  {{ formatNumber(row.avg_efficiency, 2) }}
                </template>
                <template #cell-avg_ph_deviation="{ row }">
                  {{ formatNumber(row.avg_ph_deviation, 2) }}
                </template>
                <template #cell-avg_ec_deviation="{ row }">
                  {{ formatNumber(row.avg_ec_deviation, 2) }}
                </template>
                <template #cell-avg_alerts_count="{ row }">
                  {{ formatNumber(row.avg_alerts_count, 0) }}
                </template>
                <template #cell-avg_duration_hours="{ row }">
                  {{ formatDuration(row.avg_duration_hours) }}
                </template>
              </DataTableV2>
            </div>
          </div>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import FilterBar from '@/Components/FilterBar.vue'
import PageHeader from '@/Components/PageHeader.vue'
import Pagination from '@/Components/Pagination.vue'
import TelemetryAggregatesChart from '@/Components/TelemetryAggregatesChart.vue'
import { useApi } from '@/composables/useApi'
import { logger } from '@/utils/logger'

interface ZoneOption {
  id: number
  name: string
}

interface RecipeOption {
  id: number
  name: string
}

interface AggregatePoint {
  ts: string
  avg: number
  min: number
  max: number
  median?: number
}

interface RecipeRun {
  id: number
  zone_id?: number
  zone?: { id: number; name: string }
  start_date?: string
  end_date?: string
  efficiency_score?: number
  avg_ph_deviation?: number
  avg_ec_deviation?: number
  alerts_count?: number
  total_duration_hours?: number
}

interface RecipeStats {
  avg_efficiency?: number
  avg_ph_deviation_overall?: number
  avg_ec_deviation_overall?: number
  avg_alerts_count?: number
  avg_duration_hours?: number
  total_runs?: number
}

interface RecipeComparisonRow {
  recipe_id: number
  recipe?: { id: number; name: string }
  avg_efficiency?: number
  avg_ph_deviation?: number
  avg_ec_deviation?: number
  avg_alerts_count?: number
  avg_duration_hours?: number
  runs_count?: number
}

interface SavedView {
  id: string
  name: string
  zone_id: string
  metric: string
  period: string
  recipe_id: string
}

const { api } = useApi()

const zoneOptions = ref<ZoneOption[]>([])
const recipeOptions = ref<RecipeOption[]>([])

const selectedZoneId = ref<string>('')
const selectedMetric = ref<string>('PH')
const selectedPeriod = ref<string>('24h')
const showMedian = ref<boolean>(false)

const telemetryData = ref<AggregatePoint[]>([])
const telemetryLoading = ref(false)
const telemetryError = ref<string | null>(null)

const selectedRecipeId = ref<string>('')
const recipeRuns = ref<RecipeRun[]>([])
const recipeStats = ref<RecipeStats | null>(null)
const recipeLoading = ref(false)
const recipePage = ref(1)
const recipePerPage = ref(25)
const recipeTotal = ref(0)

const compareRecipeIds = ref<string[]>([])
const comparisonRows = ref<RecipeComparisonRow[]>([])
const compareLoading = ref(false)

const savedViews = ref<SavedView[]>([])
const activeViewId = ref<string>('')
const newViewName = ref<string>('')

const metricOptions = [
  { value: 'PH', label: 'pH' },
  { value: 'EC', label: 'EC' },
  { value: 'TEMPERATURE', label: 'Температура' },
  { value: 'HUMIDITY', label: 'Влажность' },
  { value: 'WATER_LEVEL', label: 'Уровень воды' },
  { value: 'FLOW_RATE', label: 'Расход' },
]

const periodOptions = [
  { value: '1h', label: '1ч' },
  { value: '24h', label: '24ч' },
  { value: '7d', label: '7д' },
  { value: '30d', label: '30д' },
]

const selectedPeriodLabel = computed(() => {
  return periodOptions.find((p) => p.value === selectedPeriod.value)?.label || ''
})

const recipeColumns = [
  { key: 'zone', label: 'Зона' },
  { key: 'start_date', label: 'Старт', sortable: true },
  { key: 'end_date', label: 'Финиш', sortable: true },
  { key: 'efficiency_score', label: 'Эффективность', sortable: true },
  { key: 'avg_ph_deviation', label: 'ΔpH', sortable: true },
  { key: 'avg_ec_deviation', label: 'ΔEC', sortable: true },
  { key: 'alerts_count', label: 'Алерты', sortable: true },
  { key: 'total_duration_hours', label: 'Длительность', sortable: true },
]

const compareColumns = [
  { key: 'recipe_name', label: 'Рецепт' },
  { key: 'avg_efficiency', label: 'Эффективность', sortable: true },
  { key: 'avg_ph_deviation', label: 'ΔpH', sortable: true },
  { key: 'avg_ec_deviation', label: 'ΔEC', sortable: true },
  { key: 'avg_alerts_count', label: 'Алерты', sortable: true },
  { key: 'avg_duration_hours', label: 'Длительность', sortable: true },
  { key: 'runs_count', label: 'Запуски', sortable: true },
]

const formatNumber = (value: unknown, decimals: number): string => {
  if (value === null || value === undefined) return '—'
  const num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num) || !isFinite(num)) return '—'
  return num.toFixed(decimals)
}

const formatDuration = (value: unknown): string => {
  if (value === null || value === undefined) return '—'
  const num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num) || !isFinite(num)) return '—'
  if (num >= 24) {
    return `${(num / 24).toFixed(1)} дн.`
  }
  return `${num.toFixed(1)} ч`
}

const formatDate = (value?: string): string => {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ru-RU')
}

const loadZones = async (): Promise<void> => {
  try {
    const response = await api.get('/api/zones')
    const list = response?.data?.data
    zoneOptions.value = Array.isArray(list)
      ? list.map((zone: any) => ({ id: zone.id, name: zone.name || `Zone #${zone.id}` }))
      : []
  } catch (err) {
    logger.error('[Analytics] Failed to load zones', err)
  }
}

const loadRecipes = async (): Promise<void> => {
  try {
    const response = await api.get('/api/recipes')
    const payload = response?.data?.data
    const list = Array.isArray(payload?.data) ? payload.data : Array.isArray(payload) ? payload : []
    recipeOptions.value = list.map((recipe: any) => ({ id: recipe.id, name: recipe.name }))
  } catch (err) {
    logger.error('[Analytics] Failed to load recipes', err)
  }
}

const loadTelemetryAggregates = async (): Promise<void> => {
  if (!selectedZoneId.value) {
    telemetryData.value = []
    telemetryError.value = null
    return
  }

  telemetryLoading.value = true
  telemetryError.value = null

  try {
    const response = await api.get('/api/telemetry/aggregates', {
      params: {
        zone_id: Number(selectedZoneId.value),
        metric: selectedMetric.value,
        period: selectedPeriod.value,
      },
    })
    const list = response?.data?.data
    telemetryData.value = Array.isArray(list) ? list : []
  } catch (err: any) {
    telemetryError.value = 'Ошибка загрузки агрегатов'
    logger.error('[Analytics] Failed to load telemetry aggregates', err)
  } finally {
    telemetryLoading.value = false
  }
}

const loadRecipeAnalytics = async (): Promise<void> => {
  if (!selectedRecipeId.value) {
    recipeRuns.value = []
    recipeStats.value = null
    recipeTotal.value = 0
    return
  }

  recipeLoading.value = true
  try {
    const response = await api.get(`/api/recipes/${selectedRecipeId.value}/analytics`, {
      params: { page: recipePage.value },
    })
    const pageData = response?.data?.data
    const list = Array.isArray(pageData?.data) ? pageData.data : []
    recipeRuns.value = list
    recipeTotal.value = pageData?.total ?? list.length
    recipePerPage.value = pageData?.per_page ?? recipePerPage.value
    recipeStats.value = response?.data?.stats || null
  } catch (err) {
    logger.error('[Analytics] Failed to load recipe analytics', err)
  } finally {
    recipeLoading.value = false
  }
}

const loadComparison = async (): Promise<void> => {
  if (compareRecipeIds.value.length < 2) {
    comparisonRows.value = []
    return
  }

  compareLoading.value = true
  try {
    const response = await api.post('/api/recipes/comparison', {
      recipe_ids: compareRecipeIds.value.map((id) => Number(id)),
    })
    const list = response?.data?.data
    comparisonRows.value = Array.isArray(list) ? list : []
  } catch (err) {
    logger.error('[Analytics] Failed to compare recipes', err)
  } finally {
    compareLoading.value = false
  }
}

const loadSavedViews = (): void => {
  if (typeof window === 'undefined') return
  const raw = window.localStorage.getItem('analytics:views')
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      savedViews.value = parsed
    }
  } catch (err) {
    logger.warn('[Analytics] Failed to parse saved views', err)
  }
}

const persistViews = (): void => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('analytics:views', JSON.stringify(savedViews.value))
}

const applyView = (view: SavedView | undefined): void => {
  if (!view) return
  selectedZoneId.value = view.zone_id
  selectedMetric.value = view.metric
  selectedPeriod.value = view.period
  selectedRecipeId.value = view.recipe_id
}

const canSaveView = computed(() => {
  return Boolean(newViewName.value.trim())
})

const saveView = (): void => {
  if (!canSaveView.value) return
  const view: SavedView = {
    id: String(Date.now()),
    name: newViewName.value.trim(),
    zone_id: selectedZoneId.value,
    metric: selectedMetric.value,
    period: selectedPeriod.value,
    recipe_id: selectedRecipeId.value,
  }
  savedViews.value = [view, ...savedViews.value]
  activeViewId.value = view.id
  newViewName.value = ''
  persistViews()
}

const deleteView = (): void => {
  if (!activeViewId.value) return
  savedViews.value = savedViews.value.filter((view) => view.id !== activeViewId.value)
  activeViewId.value = ''
  persistViews()
}

watch(activeViewId, (value) => {
  if (!value) return
  const view = savedViews.value.find((item) => item.id === value)
  applyView(view)
})

watch(savedViews, () => {
  persistViews()
})

watch([selectedZoneId, selectedMetric, selectedPeriod], () => {
  loadTelemetryAggregates()
})

watch([selectedRecipeId, recipePage], () => {
  loadRecipeAnalytics()
})

watch(selectedRecipeId, () => {
  recipePage.value = 1
})

onMounted(async () => {
  loadSavedViews()
  await Promise.all([loadZones(), loadRecipes()])
  if (selectedZoneId.value) {
    loadTelemetryAggregates()
  }
  if (selectedRecipeId.value) {
    loadRecipeAnalytics()
  }
})
</script>
