import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { SimulationInitialState } from '@/composables/useSimulationSubmit'

interface ApiClient {
  get<T = unknown>(url: string, config?: Record<string, unknown>): Promise<{ data?: T }>
}

export interface RecipeOption {
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

interface UseSimulationRecipesParams {
  api: ApiClient
  isOpen: Ref<boolean>
  defaultRecipeId: Ref<number | null | undefined>
  selectedRecipeId: Ref<number | null>
  initialState: SimulationInitialState
}

function toNumberOrNull(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function extractRecipeDefaults(recipe: unknown): RecipeDefaults | null {
  if (!recipe || typeof recipe !== 'object') return null
  const recipePayload = recipe as Record<string, unknown>
  const phases = Array.isArray(recipePayload.phases) ? recipePayload.phases : []
  if (!phases.length) return null

  const sorted = [...phases].sort((a, b) => {
    const left = typeof (a as Record<string, unknown>).phase_index === 'number'
      ? ((a as Record<string, unknown>).phase_index as number)
      : 0
    const right = typeof (b as Record<string, unknown>).phase_index === 'number'
      ? ((b as Record<string, unknown>).phase_index as number)
      : 0
    return left - right
  })

  const phase = (sorted[0] ?? {}) as Record<string, any>

  return {
    ph: toNumberOrNull(
      phase.ph_target ?? phase.ph_min ?? phase.ph_max ?? phase.targets?.ph?.min ?? phase.targets?.ph?.max
    ),
    ec: toNumberOrNull(
      phase.ec_target ?? phase.ec_min ?? phase.ec_max ?? phase.targets?.ec?.min ?? phase.targets?.ec?.max
    ),
    temp_air: toNumberOrNull(
      phase.temp_air_target ?? phase.targets?.climate?.temperature?.target ?? phase.targets?.climate?.temperature
    ),
    temp_water: toNumberOrNull(
      phase.temp_water_target ?? phase.extensions?.temp_water_target ?? phase.extensions?.temp_water
    ),
    humidity_air: toNumberOrNull(
      phase.humidity_target ?? phase.targets?.climate?.humidity?.target ?? phase.targets?.climate?.humidity
    ),
  }
}

export function useSimulationRecipes(params: UseSimulationRecipesParams) {
  const recipes = ref<RecipeOption[]>([])
  const recipesLoading = ref(false)
  const recipesError = ref<string | null>(null)
  const recipeSearch = ref('')
  const effectiveRecipeId = computed(() => params.selectedRecipeId.value ?? params.defaultRecipeId.value ?? null)

  const recipeDefaultsCache = new Map<number, RecipeDefaults>()
  const lastDefaultsRecipeId = ref<number | null>(null)
  let recipeSearchTimer: ReturnType<typeof setTimeout> | null = null

  const applyRecipeDefaults = (defaults: RecipeDefaults | null): void => {
    if (!defaults) return
    if (params.initialState.ph === null && defaults.ph !== null && defaults.ph !== undefined) {
      params.initialState.ph = defaults.ph
    }
    if (params.initialState.ec === null && defaults.ec !== null && defaults.ec !== undefined) {
      params.initialState.ec = defaults.ec
    }
    if (params.initialState.temp_air === null && defaults.temp_air !== null && defaults.temp_air !== undefined) {
      params.initialState.temp_air = defaults.temp_air
    }
    if (params.initialState.temp_water === null && defaults.temp_water !== null && defaults.temp_water !== undefined) {
      params.initialState.temp_water = defaults.temp_water
    }
    if (params.initialState.humidity_air === null && defaults.humidity_air !== null && defaults.humidity_air !== undefined) {
      params.initialState.humidity_air = defaults.humidity_air
    }
  }

  const addRecipeIfMissing = (recipe: RecipeOption): void => {
    if (!recipes.value.find((item) => item.id === recipe.id)) {
      recipes.value.push(recipe)
    }
  }

  const ensureDefaultRecipe = async (): Promise<void> => {
    const fallbackRecipeId = params.defaultRecipeId.value
    if (!fallbackRecipeId) return
    if (recipes.value.find((item) => item.id === fallbackRecipeId)) return

    try {
      const response = await params.api.get<{ status: string; data?: { id: number; name: string } }>(
        `/recipes/${fallbackRecipeId}`
      )
      const data = response.data?.data
      if (data?.id && data?.name) {
        addRecipeIfMissing({ id: data.id, name: data.name })
      }
    } catch (err) {
      logger.debug('[ZoneSimulationModal] Failed to load default recipe', err)
    }
  }

  const loadRecipes = async (search?: string): Promise<void> => {
    recipesLoading.value = true
    recipesError.value = null
    try {
      const response = await params.api.get<{ status: string; data?: { data?: RecipeOption[] } }>(
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

  const loadRecipeDefaults = async (recipeId: number): Promise<void> => {
    if (recipeDefaultsCache.has(recipeId)) {
      applyRecipeDefaults(recipeDefaultsCache.get(recipeId) || null)
      return
    }

    try {
      const response = await params.api.get<{ status: string; data?: unknown }>(`/recipes/${recipeId}`)
      const defaults = extractRecipeDefaults(response.data?.data)
      if (defaults) {
        recipeDefaultsCache.set(recipeId, defaults)
      }
      applyRecipeDefaults(defaults)
    } catch (err) {
      logger.debug('[ZoneSimulationModal] Failed to load recipe defaults', err)
    }
  }

  const handleOpen = async (): Promise<void> => {
    await loadRecipes(recipeSearch.value.trim())
  }

  watch(
    () => params.defaultRecipeId.value,
    (recipeId) => {
      if (recipeId && params.selectedRecipeId.value === null) {
        params.selectedRecipeId.value = recipeId
      }
    }
  )

  watch(recipeSearch, (value) => {
    if (!params.isOpen.value) return
    if (recipeSearchTimer) {
      clearTimeout(recipeSearchTimer)
    }
    recipeSearchTimer = setTimeout(() => {
      void loadRecipes(value.trim())
    }, 300)
  })

  watch(
    () => [params.isOpen.value, effectiveRecipeId.value] as const,
    ([isOpen, recipeId]) => {
      if (!isOpen || !recipeId) return
      if (lastDefaultsRecipeId.value === recipeId) return
      lastDefaultsRecipeId.value = recipeId
      void loadRecipeDefaults(recipeId)
    }
  )

  onUnmounted(() => {
    if (recipeSearchTimer) {
      clearTimeout(recipeSearchTimer)
      recipeSearchTimer = null
    }
  })

  return {
    recipes,
    recipesLoading,
    recipesError,
    recipeSearch,
    effectiveRecipeId,
    handleOpen,
  }
}
