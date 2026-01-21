<template>
  <div
    v-if="show"
    class="fixed inset-0 z-50 flex items-center justify-center"
  >
    <div
      class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80"
      @click="$emit('close')"
    ></div>
    <div
      class="relative w-full max-w-2xl rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-6 max-h-[90vh] overflow-y-auto"
      @click.stop
    >
      <h2 class="text-lg font-semibold mb-4">
        Симуляция цифрового двойника
      </h2>
      
      <form
        class="space-y-4"
        @submit.prevent="onSubmit"
        @click.stop
      >
        <div>
          <label
            for="simulation-duration-hours"
            class="block text-sm font-medium mb-1"
          >Длительность (часы)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Сколько часов моделировать. Дольше = более долгий прогноз.
          </p>
          <input
            id="simulation-duration-hours"
            v-model.number="form.duration_hours"
            name="duration_hours"
            type="number"
            min="1"
            max="720"
            class="input-field h-9 w-full"
            required
          />
        </div>
        
        <div>
          <label
            for="simulation-step-minutes"
            class="block text-sm font-medium mb-1"
          >Шаг (минуты)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Меньше шаг — выше детализация, но расчет дольше.
          </p>
          <input
            id="simulation-step-minutes"
            v-model.number="form.step_minutes"
            name="step_minutes"
            type="number"
            min="1"
            max="60"
            class="input-field h-9 w-full"
            required
          />
        </div>
        
        <div>
          <label
            for="simulation-recipe-search"
            class="block text-sm font-medium mb-1"
          >Рецепт (необязательно)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Выберите рецепт из базы или оставьте "по умолчанию", чтобы взять рецепт зоны.
          </p>
          <input
            id="simulation-recipe-search"
            v-model="recipeSearch"
            name="recipe_search"
            type="text"
            placeholder="Поиск по названию..."
            class="input-field h-9 w-full mb-2"
          />
          <select
            id="simulation-recipe-select"
            v-model="form.recipe_id"
            name="recipe_id"
            class="input-field h-9 w-full"
          >
            <option :value="null">
              Рецепт зоны (по умолчанию)
            </option>
            <option
              v-for="recipe in recipes"
              :key="recipe.id"
              :value="recipe.id"
            >
              {{ recipe.name }}
            </option>
          </select>
          <div
            v-if="recipesLoading"
            class="text-xs text-[color:var(--text-muted)] mt-1"
          >
            Загрузка рецептов...
          </div>
          <div
            v-else-if="recipesError"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ recipesError }}
          </div>
        </div>
        
        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-sm font-medium mb-2">
            Начальные условия (необязательно)
          </div>
          <p class="text-xs text-[color:var(--text-muted)] mb-2">
            Заполните только то, что хотите переопределить. Пустые поля возьмутся из текущих данных.
          </p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label
                for="simulation-initial-ph"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >pH</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Обычно 5.5–6.5 для гидропоники.
              </p>
              <input
                id="simulation-initial-ph"
                v-model.number="form.initial_state.ph"
                name="initial_state_ph"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-ec"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >EC</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Электропроводность раствора (мСм/см).
              </p>
              <input
                id="simulation-initial-ec"
                v-model.number="form.initial_state.ec"
                name="initial_state_ec"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-temp-air"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Температура воздуха (°C)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Стартовая температура воздуха в зоне.
              </p>
              <input
                id="simulation-initial-temp-air"
                v-model.number="form.initial_state.temp_air"
                name="initial_state_temp_air"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-temp-water"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Температура воды (°C)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Температура питательного раствора.
              </p>
              <input
                id="simulation-initial-temp-water"
                v-model.number="form.initial_state.temp_water"
                name="initial_state_temp_water"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
            <div class="col-span-2">
              <label
                for="simulation-initial-humidity"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Влажность (%)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Относительная влажность воздуха.
              </p>
              <input
                id="simulation-initial-humidity"
                v-model.number="form.initial_state.humidity_air"
                name="initial_state_humidity_air"
                type="number"
                step="0.1"
                class="input-field h-8 w-full"
              />
            </div>
          </div>
        </div>
        
        <div
          v-if="isSimulating"
          class="space-y-2"
        >
          <div class="text-xs text-[color:var(--text-muted)]">
            Статус: {{ simulationStatusLabel }}
          </div>
          <div class="relative w-full h-2 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
            <div
              class="relative h-2 bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
              :style="{ width: `${simulationProgress}%` }"
            >
              <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.2),transparent)] simulation-shimmer"></div>
            </div>
          </div>
        </div>
        
        <div
          v-if="error"
          class="text-sm text-[color:var(--accent-red)]"
        >
          {{ error }}
        </div>
        
        <div class="flex justify-end gap-2 pt-4 border-t border-[color:var(--border-muted)]">
          <Button
            type="button"
            variant="secondary"
            @click="$emit('close')"
          >
            Отмена
          </Button>
          <Button
            type="submit"
            :disabled="loading"
          >
            {{ loading ? 'Запуск...' : 'Запустить' }}
          </Button>
        </div>
      </form>
      
      <div
        v-if="results"
        class="mt-6 border-t border-[color:var(--border-muted)] pt-4"
        @click.stop
      >
        <div class="text-sm font-medium mb-3">
          Результаты симуляции
        </div>
        <div class="text-xs text-[color:var(--text-muted)] mb-2">
          Длительность: {{ resultDurationHours }} ч, шаг: {{ resultStepMinutes }} мин
        </div>
        <div class="h-64">
          <ChartBase
            v-if="chartOption"
            :option="chartOption"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onUnmounted } from 'vue'
import { logger } from '@/utils/logger'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useLoading } from '@/composables/useLoading'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useTheme } from '@/composables/useTheme'
import type { EChartsOption } from 'echarts'

interface Props {
  show?: boolean
  zoneId: number
  defaultRecipeId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  defaultRecipeId: null,
})

defineEmits<{
  close: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)
const { theme } = useTheme()

interface SimulationForm {
  duration_hours: number
  step_minutes: number
  recipe_id: number | null
  initial_state: {
    ph: number | null
    ec: number | null
    temp_air: number | null
    temp_water: number | null
    humidity_air: number | null
  }
}

interface SimulationPoint {
  t: number
  ph: number
  ec: number
  temp_air: number
}

interface SimulationResults {
  duration_hours?: number
  step_minutes?: number
  points: SimulationPoint[]
}

interface RecipeOption {
  id: number
  name: string
}

interface RecipeDefaults {
  ph?: number | null
  ec?: number | null
  temp_air?: number | null
  temp_water?: number | null
  humidity_air?: number | null
}

const form = reactive<SimulationForm>({
  duration_hours: 72,
  step_minutes: 10,
  recipe_id: props.defaultRecipeId || null,
  initial_state: {
    ph: null,
    ec: null,
    temp_air: null,
    temp_water: null,
    humidity_air: null,
  },
})

const { loading, startLoading, stopLoading } = useLoading<boolean>(false)
const error = ref<string | null>(null)
const results = ref<SimulationResults | null>(null)
const recipes = ref<RecipeOption[]>([])
const recipesLoading = ref(false)
const recipesError = ref<string | null>(null)
const recipeSearch = ref('')
let recipeSearchTimer: ReturnType<typeof setTimeout> | null = null
const lastDefaultsRecipeId = ref<number | null>(null)
const recipeDefaultsCache = new Map<number, RecipeDefaults>()
const simulationJobId = ref<string | null>(null)
const simulationStatus = ref<'idle' | 'queued' | 'processing' | 'completed' | 'failed'>('idle')
let simulationPollTimer: ReturnType<typeof setInterval> | null = null

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return {
    text: resolveCssColor('--text-muted', '#9ca3af'),
    textStrong: resolveCssColor('--text-primary', '#e5e7eb'),
    grid: resolveCssColor('--border-muted', '#374151'),
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
    temp: resolveCssColor('--accent-amber', '#f59e0b'),
  }
})

const chartOption = computed<EChartsOption | null>(() => {
  if (!results.value?.points) return null
  
  const points = results.value.points
  const phData = points.map(p => [p.t, p.ph])
  const ecData = points.map(p => [p.t, p.ec])
  const tempData = points.map(p => [p.t, p.temp_air])
  
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['pH', 'EC', 'Температура воздуха'],
      textStyle: { color: chartPalette.value.textStrong },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: 'Время (ч)',
      nameTextStyle: { color: chartPalette.value.text },
      axisLabel: { color: chartPalette.value.text },
      splitLine: { lineStyle: { color: chartPalette.value.grid } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'pH / EC',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { lineStyle: { color: chartPalette.value.grid } },
      },
      {
        type: 'value',
        name: 'Температура (°C)',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'pH',
        type: 'line',
        data: phData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ph },
        itemStyle: { color: chartPalette.value.ph },
      },
      {
        name: 'EC',
        type: 'line',
        data: ecData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ec },
        itemStyle: { color: chartPalette.value.ec },
      },
      {
        name: 'Температура воздуха',
        type: 'line',
        yAxisIndex: 1,
        data: tempData,
        smooth: true,
        lineStyle: { color: chartPalette.value.temp },
        itemStyle: { color: chartPalette.value.temp },
      },
    ],
  }
})

const simulationProgress = computed(() => {
  switch (simulationStatus.value) {
    case 'queued':
      return 20
    case 'processing':
      return 60
    case 'completed':
      return 100
    case 'failed':
      return 100
    default:
      return 0
  }
})

const simulationStatusLabel = computed(() => {
  switch (simulationStatus.value) {
    case 'queued':
      return 'В очереди'
    case 'processing':
      return 'Выполняется'
    case 'completed':
      return 'Завершено'
    case 'failed':
      return 'Ошибка'
    default:
      return ''
  }
})

const isSimulating = computed(() => {
  return simulationStatus.value === 'queued' || simulationStatus.value === 'processing' || loading.value
})

const resultDurationHours = computed(() => {
  return results.value?.duration_hours ?? form.duration_hours
})

const resultStepMinutes = computed(() => {
  return results.value?.step_minutes ?? form.step_minutes
})

function toNumberOrNull(value: unknown): number | null {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function extractRecipeDefaults(recipe: any): RecipeDefaults | null {
  const phases = Array.isArray(recipe?.phases) ? recipe.phases : []
  if (phases.length === 0) return null
  const sorted = [...phases].sort((a, b) => (a.phase_index ?? 0) - (b.phase_index ?? 0))
  const phase = sorted[0]

  return {
    ph: toNumberOrNull(
      phase?.ph_target ?? phase?.ph_min ?? phase?.ph_max ?? phase?.targets?.ph?.min ?? phase?.targets?.ph?.max
    ),
    ec: toNumberOrNull(
      phase?.ec_target ?? phase?.ec_min ?? phase?.ec_max ?? phase?.targets?.ec?.min ?? phase?.targets?.ec?.max
    ),
    temp_air: toNumberOrNull(
      phase?.temp_air_target ?? phase?.targets?.climate?.temperature?.target ?? phase?.targets?.climate?.temperature
    ),
    temp_water: toNumberOrNull(
      phase?.temp_water_target ?? phase?.extensions?.temp_water_target ?? phase?.extensions?.temp_water
    ),
    humidity_air: toNumberOrNull(
      phase?.humidity_target ?? phase?.targets?.climate?.humidity?.target ?? phase?.targets?.climate?.humidity
    ),
  }
}

function applyRecipeDefaults(defaults: RecipeDefaults | null): void {
  if (!defaults) return
  if (form.initial_state.ph === null && defaults.ph !== null && defaults.ph !== undefined) {
    form.initial_state.ph = defaults.ph
  }
  if (form.initial_state.ec === null && defaults.ec !== null && defaults.ec !== undefined) {
    form.initial_state.ec = defaults.ec
  }
  if (form.initial_state.temp_air === null && defaults.temp_air !== null && defaults.temp_air !== undefined) {
    form.initial_state.temp_air = defaults.temp_air
  }
  if (form.initial_state.temp_water === null && defaults.temp_water !== null && defaults.temp_water !== undefined) {
    form.initial_state.temp_water = defaults.temp_water
  }
  if (form.initial_state.humidity_air === null && defaults.humidity_air !== null && defaults.humidity_air !== undefined) {
    form.initial_state.humidity_air = defaults.humidity_air
  }
}

function addRecipeIfMissing(recipe: RecipeOption): void {
  if (!recipes.value.find((item) => item.id === recipe.id)) {
    recipes.value.push(recipe)
  }
}

async function ensureDefaultRecipe(): Promise<void> {
  if (!props.defaultRecipeId) return
  if (recipes.value.find((item) => item.id === props.defaultRecipeId)) return

  try {
    const response = await api.get<{ status: string; data?: { id: number; name: string } }>(
      `/recipes/${props.defaultRecipeId}`
    )
    const data = response.data?.data
    if (data?.id && data?.name) {
      addRecipeIfMissing({ id: data.id, name: data.name })
    }
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Failed to load default recipe', err)
  }
}

async function loadRecipes(search?: string): Promise<void> {
  recipesLoading.value = true
  recipesError.value = null
  try {
    const response = await api.get<{ status: string; data?: { data?: RecipeOption[] } }>(
      '/recipes',
      {
        params: search ? { search } : {},
      }
    )
    const items = response.data?.data?.data || []
    recipes.value = items.map((item) => ({
      id: item.id,
      name: item.name,
    }))
    await ensureDefaultRecipe()
  } catch (err) {
    logger.error('[ZoneSimulationModal] Failed to load recipes', err)
    recipesError.value = 'Не удалось загрузить список рецептов'
  } finally {
    recipesLoading.value = false
  }
}

async function loadRecipeDefaults(recipeId: number): Promise<void> {
  if (recipeDefaultsCache.has(recipeId)) {
    applyRecipeDefaults(recipeDefaultsCache.get(recipeId) || null)
    return
  }

  try {
    const response = await api.get<{ status: string; data?: any }>(`/recipes/${recipeId}`)
    const data = response.data?.data
    const defaults = extractRecipeDefaults(data)
    if (defaults) {
      recipeDefaultsCache.set(recipeId, defaults)
    }
    applyRecipeDefaults(defaults)
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Failed to load recipe defaults', err)
  }
}

const effectiveRecipeId = computed(() => form.recipe_id ?? props.defaultRecipeId ?? null)

function normalizeSimulationResult(payload: any): SimulationResults | null {
  if (!payload || typeof payload !== 'object') return null
  if (Array.isArray(payload.points)) {
    return payload as SimulationResults
  }
  if (payload.data && Array.isArray(payload.data.points)) {
    return payload.data as SimulationResults
  }
  if (payload.result && Array.isArray(payload.result.points)) {
    return payload.result as SimulationResults
  }
  if (payload.result?.data && Array.isArray(payload.result.data.points)) {
    return payload.result.data as SimulationResults
  }
  return null
}

function clearSimulationPolling(): void {
  if (simulationPollTimer) {
    clearInterval(simulationPollTimer)
    simulationPollTimer = null
  }
}

async function pollSimulationStatus(jobId: string): Promise<void> {
  try {
    const response = await api.get<{ status: string; data?: any }>(`/simulations/${jobId}`)
    const data = response.data?.data
    if (!data) return

    const status = data.status as typeof simulationStatus.value | undefined
    if (status) {
      simulationStatus.value = status
    }

    if (status === 'completed') {
      const parsed = normalizeSimulationResult(data.result)
      if (parsed) {
        results.value = parsed
      }
      stopLoading()
      clearSimulationPolling()
      return
    }

    if (status === 'failed') {
      error.value = data.error || 'Симуляция завершилась с ошибкой'
      stopLoading()
      clearSimulationPolling()
    }
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Simulation status poll failed', err)
  }
}

function startSimulationPolling(jobId: string): void {
  clearSimulationPolling()
  pollSimulationStatus(jobId)
  simulationPollTimer = setInterval(() => {
    pollSimulationStatus(jobId)
  }, 2000)
}

watch(
  () => props.show,
  (isOpen) => {
    if (isOpen) {
      loadRecipes(recipeSearch.value.trim())
      if (effectiveRecipeId.value) {
        loadRecipeDefaults(effectiveRecipeId.value)
      }
    } else {
      clearSimulationPolling()
    }
  }
)

watch(recipeSearch, (value) => {
  if (!props.show) return
  if (recipeSearchTimer) {
    clearTimeout(recipeSearchTimer)
  }
  recipeSearchTimer = setTimeout(() => {
    loadRecipes(value.trim())
  }, 300)
})

watch(
  () => [props.show, effectiveRecipeId.value] as const,
  ([isOpen, recipeId]) => {
    if (!isOpen || !recipeId) return
    if (lastDefaultsRecipeId.value === recipeId) return
    lastDefaultsRecipeId.value = recipeId
    loadRecipeDefaults(recipeId)
  }
)

onUnmounted(() => {
  clearSimulationPolling()
})

async function onSubmit(): Promise<void> {
  startLoading()
  error.value = null
  results.value = null
  simulationJobId.value = null
  simulationStatus.value = 'queued'
  
  try {
    interface SimulationPayload {
      duration_hours: number
      step_minutes: number
      recipe_id?: number
      initial_state?: Partial<SimulationForm['initial_state']>
    }
    
    const payload: SimulationPayload = {
      duration_hours: form.duration_hours,
      step_minutes: form.step_minutes,
    }
    
    if (form.recipe_id) {
      payload.recipe_id = form.recipe_id
    }
    
    // Фильтруем initial_state, убирая null значения
    const initialState: Partial<SimulationForm['initial_state']> = {}
    if (form.initial_state.ph !== null) initialState.ph = form.initial_state.ph
    if (form.initial_state.ec !== null) initialState.ec = form.initial_state.ec
    if (form.initial_state.temp_air !== null) initialState.temp_air = form.initial_state.temp_air
    if (form.initial_state.temp_water !== null) initialState.temp_water = form.initial_state.temp_water
    if (form.initial_state.humidity_air !== null) initialState.humidity_air = form.initial_state.humidity_air
    
    if (Object.keys(initialState).length > 0) {
      payload.initial_state = initialState
    }
    
    const response = await api.post<{ status: string; data?: any }>(
      `/zones/${props.zoneId}/simulate`,
      payload
    )
    
    const responseData = response.data?.data
    if (response.data?.status === 'ok' && responseData) {
      if (responseData.job_id) {
        simulationJobId.value = responseData.job_id
        simulationStatus.value = responseData.status || 'queued'
        startSimulationPolling(responseData.job_id)
        showToast('Симуляция поставлена в очередь', 'info', TOAST_TIMEOUT.NORMAL)
        return
      }

      const parsed = normalizeSimulationResult(responseData)
      if (parsed) {
        results.value = parsed
        simulationStatus.value = 'completed'
        showToast('Симуляция успешно завершена', 'success', TOAST_TIMEOUT.NORMAL)
      } else {
        error.value = 'Неожиданный формат ответа'
        simulationStatus.value = 'failed'
      }
    } else {
      error.value = 'Неожиданный формат ответа'
      simulationStatus.value = 'failed'
    }
  } catch (err) {
    logger.error('[ZoneSimulationModal] Simulation error:', err)
    const errorMsg = err instanceof Error ? err.message : 'Не удалось запустить симуляцию'
    error.value = errorMsg
    simulationStatus.value = 'failed'
  } finally {
    if (simulationStatus.value !== 'queued' && simulationStatus.value !== 'processing') {
      stopLoading()
    }
  }
}
</script>

<style scoped>
@keyframes simulation-shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.simulation-shimmer {
  animation: simulation-shimmer 1.6s infinite;
}
</style>
