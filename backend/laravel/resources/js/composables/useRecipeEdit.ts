import { computed, onMounted, ref } from 'vue'
import { usePage, router, useForm } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { NutrientProduct, Recipe, RecipePhase } from '@/types'

const DEFAULT_NUTRIENT_PROGRAM_CODE = 'YARAREGA_CALCINIT_HAIFA_MICRO_V1'
const DEFAULT_NUTRIENT_DOSE_DELAY_SEC = 12
const DEFAULT_NUTRIENT_EC_STOP_TOLERANCE = 0.07

export interface RecipePhaseForm {
  id?: number
  phase_index: number
  name: string
  duration_hours: number
  nutrient_program_code: string | null
  nutrient_mode: 'ratio_ec_pid' | 'delta_ec_by_k' | 'dose_ml_l_only'
  nutrient_npk_ratio_pct: number | null
  nutrient_calcium_ratio_pct: number | null
  nutrient_magnesium_ratio_pct: number | null
  nutrient_micro_ratio_pct: number | null
  nutrient_npk_dose_ml_l: number | null
  nutrient_calcium_dose_ml_l: number | null
  nutrient_magnesium_dose_ml_l: number | null
  nutrient_micro_dose_ml_l: number | null
  nutrient_npk_product_id: number | null
  nutrient_calcium_product_id: number | null
  nutrient_magnesium_product_id: number | null
  nutrient_micro_product_id: number | null
  nutrient_dose_delay_sec: number | null
  nutrient_ec_stop_tolerance: number | null
  nutrient_solution_volume_l: number | null
  targets: {
    ph: { min: number; max: number }
    ec: { min: number; max: number }
    temp_air: number | null
    humidity_air: number | null
    light_hours: number | null
    irrigation_interval_sec: number | null
    irrigation_duration_sec: number | null
  }
}

export interface RecipeFormData {
  name: string
  description: string
  plant_id: number | null
  phases: RecipePhaseForm[]
}

interface PageProps {
  recipe?: Recipe
  [key: string]: unknown
}

export interface PlantOption {
  id: number
  name: string
}

function toNullableNumber(value: unknown, fallback: number | null = null): number | null {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function toNullableInt(value: unknown, fallback: number | null = null): number | null {
  const parsed = toNullableNumber(value, fallback)
  if (parsed === null) {
    return null
  }

  return Math.round(parsed)
}

function createDefaultPhase(phaseIndex: number): RecipePhaseForm {
  return {
    phase_index: phaseIndex,
    name: '',
    duration_hours: 24,
    nutrient_program_code: DEFAULT_NUTRIENT_PROGRAM_CODE,
    nutrient_mode: 'ratio_ec_pid',
    nutrient_npk_ratio_pct: 44,
    nutrient_calcium_ratio_pct: 36,
    nutrient_magnesium_ratio_pct: 17,
    nutrient_micro_ratio_pct: 3,
    nutrient_npk_dose_ml_l: 0.55,
    nutrient_calcium_dose_ml_l: 0.55,
    nutrient_magnesium_dose_ml_l: 0.25,
    nutrient_micro_dose_ml_l: 0.09,
    nutrient_npk_product_id: null,
    nutrient_calcium_product_id: null,
    nutrient_magnesium_product_id: null,
    nutrient_micro_product_id: null,
    nutrient_dose_delay_sec: DEFAULT_NUTRIENT_DOSE_DELAY_SEC,
    nutrient_ec_stop_tolerance: DEFAULT_NUTRIENT_EC_STOP_TOLERANCE,
    nutrient_solution_volume_l: null,
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.2, max: 1.6 },
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null,
    },
  }
}

function mapRecipePhaseToForm(phase: RecipePhase): RecipePhaseForm {
  const phMin = toNullableNumber(phase.ph_min ?? phase.targets?.ph?.min, 5.8) ?? 5.8
  const phMax = toNullableNumber(phase.ph_max ?? phase.targets?.ph?.max, 6.0) ?? 6.0
  const ecMin = toNullableNumber(phase.ec_min ?? phase.targets?.ec?.min, 1.2) ?? 1.2
  const ecMax = toNullableNumber(phase.ec_max ?? phase.targets?.ec?.max, 1.6) ?? 1.6

  return {
    id: phase.id,
    phase_index: phase.phase_index || 0,
    name: phase.name || '',
    duration_hours: phase.duration_hours || 24,
    nutrient_program_code: typeof phase.nutrient_program_code === 'string' && phase.nutrient_program_code.trim().length > 0
      ? phase.nutrient_program_code
      : DEFAULT_NUTRIENT_PROGRAM_CODE,
    nutrient_mode: (phase.nutrient_mode === 'delta_ec_by_k' || phase.nutrient_mode === 'dose_ml_l_only')
      ? phase.nutrient_mode
      : 'ratio_ec_pid',
    nutrient_npk_ratio_pct: toNullableNumber(phase.nutrient_npk_ratio_pct, 44),
    nutrient_calcium_ratio_pct: toNullableNumber(phase.nutrient_calcium_ratio_pct, 36),
    nutrient_magnesium_ratio_pct: toNullableNumber(phase.nutrient_magnesium_ratio_pct, 17),
    nutrient_micro_ratio_pct: toNullableNumber(phase.nutrient_micro_ratio_pct, 3),
    nutrient_npk_dose_ml_l: toNullableNumber(phase.nutrient_npk_dose_ml_l, 0.55),
    nutrient_calcium_dose_ml_l: toNullableNumber(phase.nutrient_calcium_dose_ml_l, 0.55),
    nutrient_magnesium_dose_ml_l: toNullableNumber(phase.nutrient_magnesium_dose_ml_l, 0.25),
    nutrient_micro_dose_ml_l: toNullableNumber(phase.nutrient_micro_dose_ml_l, 0.09),
    nutrient_npk_product_id: toNullableInt(phase.nutrient_npk_product_id),
    nutrient_calcium_product_id: toNullableInt(phase.nutrient_calcium_product_id),
    nutrient_magnesium_product_id: toNullableInt(phase.nutrient_magnesium_product_id),
    nutrient_micro_product_id: toNullableInt(phase.nutrient_micro_product_id),
    nutrient_dose_delay_sec: toNullableInt(phase.nutrient_dose_delay_sec, DEFAULT_NUTRIENT_DOSE_DELAY_SEC),
    nutrient_ec_stop_tolerance: toNullableNumber(phase.nutrient_ec_stop_tolerance, DEFAULT_NUTRIENT_EC_STOP_TOLERANCE),
    nutrient_solution_volume_l: toNullableNumber(phase.nutrient_solution_volume_l),
    targets: {
      ph: { min: phMin, max: phMax },
      ec: { min: ecMin, max: ecMax },
      temp_air: toNullableNumber(phase.temp_air_target ?? phase.targets?.temp_air),
      humidity_air: toNullableNumber(phase.humidity_target ?? phase.targets?.humidity_air),
      light_hours: toNullableNumber(phase.lighting_photoperiod_hours ?? phase.targets?.light_hours),
      irrigation_interval_sec: toNullableInt(phase.irrigation_interval_sec ?? phase.targets?.irrigation_interval_sec),
      irrigation_duration_sec: toNullableInt(phase.irrigation_duration_sec ?? phase.targets?.irrigation_duration_sec),
    },
  }
}

export function useRecipeEdit() {
  const { showToast } = useToast()
  const { api } = useApi(showToast)
  const page = usePage<PageProps>()
  const recipe = (page.props.recipe || {}) as Partial<Recipe>

  const plants = ref<PlantOption[]>([])
  const plantsLoading = ref(false)
  const nutrientProducts = ref<NutrientProduct[]>([])
  const nutrientProductsLoading = ref(false)
  const initialPlantId = recipe.plants?.[0]?.id ?? null

  const form = useForm<RecipeFormData>({
    name: recipe.name || '',
    description: recipe.description || '',
    plant_id: initialPlantId,
    phases: (recipe.phases || []).length > 0
      ? (recipe.phases || []).map((phase) => mapRecipePhaseToForm(phase))
      : [createDefaultPhase(0)],
  })

  const npkProducts = computed<NutrientProduct[]>(() => {
    return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'npk')
  })

  const calciumProducts = computed<NutrientProduct[]>(() => {
    return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'calcium')
  })

  const magnesiumProducts = computed<NutrientProduct[]>(() => {
    return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'magnesium')
  })

  const microProducts = computed<NutrientProduct[]>(() => {
    return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'micro')
  })

  const sortedPhases = computed<RecipePhaseForm[]>(() => {
    return [...form.phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
  })

  const loadPlants = async (): Promise<void> => {
    try {
      plantsLoading.value = true
      const response = await api.get('/plants')
      const data = response.data?.data || []
      plants.value = Array.isArray(data)
        ? data.map((plant: Record<string, unknown>) => ({ id: plant.id as number, name: plant.name as string }))
        : []

      if (!form.plant_id && recipe.id) {
        const recipeResponse = await api.get(`/recipes/${recipe.id}`)
        const recipeData = recipeResponse.data?.data || {}
        const apiPlantId = (recipeData as { plants?: Array<{ id: number }> }).plants?.[0]?.id ?? null
        if (apiPlantId) {
          form.plant_id = apiPlantId
        }
      }

      if (!form.plant_id && plants.value.length === 1) {
        form.plant_id = plants.value[0].id
      }
    } catch (error) {
      logger.error('Failed to load plants:', error)
      showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      plantsLoading.value = false
    }
  }

  const loadNutrientProducts = async (): Promise<void> => {
    try {
      nutrientProductsLoading.value = true
      const response = await api.get('/nutrient-products')
      const data = response.data?.data || []

      nutrientProducts.value = Array.isArray(data)
        ? data.map((item: Record<string, unknown>) => ({
          id: item.id as number,
          manufacturer: item.manufacturer as string,
          name: item.name as string,
          component: item.component as NutrientProduct['component'],
          composition: (item.composition as string | null) ?? null,
          recommended_stage: (item.recommended_stage as string | null) ?? null,
          notes: (item.notes as string | null) ?? null,
          metadata: (item.metadata as Record<string, unknown> | null) ?? null,
        }))
        : []
    } catch (error) {
      logger.error('Failed to load nutrient products:', error)
      showToast('Не удалось загрузить список удобрений', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      nutrientProductsLoading.value = false
    }
  }

  function nutrientRatioSum(phase: RecipePhaseForm): number {
    const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
    const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
    const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
    const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0
    return npk + calcium + magnesium + micro
  }

  function roundRatio(value: number): number {
    return Math.round(value * 100) / 100
  }

  function normalizePhaseRatios(phase: RecipePhaseForm): void {
    const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
    const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
    const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
    const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0

    const sum = npk + calcium + magnesium + micro
    if (sum <= 0) {
      phase.nutrient_npk_ratio_pct = 44
      phase.nutrient_calcium_ratio_pct = 36
      phase.nutrient_magnesium_ratio_pct = 17
      phase.nutrient_micro_ratio_pct = 3
      return
    }

    const normalizedNpk = roundRatio((npk / sum) * 100)
    const normalizedCalcium = roundRatio((calcium / sum) * 100)
    const normalizedMagnesium = roundRatio((magnesium / sum) * 100)
    let normalizedMicro = roundRatio(100 - normalizedNpk - normalizedCalcium - normalizedMagnesium)

    if (normalizedMicro < 0) {
      normalizedMicro = 0
    }

    const normalizedSum = normalizedNpk + normalizedCalcium + normalizedMagnesium + normalizedMicro
    if (Math.abs(normalizedSum - 100) > 0.01) {
      normalizedMicro = roundRatio(normalizedMicro + (100 - normalizedSum))
    }

    phase.nutrient_npk_ratio_pct = normalizedNpk
    phase.nutrient_calcium_ratio_pct = normalizedCalcium
    phase.nutrient_magnesium_ratio_pct = normalizedMagnesium
    phase.nutrient_micro_ratio_pct = normalizedMicro
  }

  function isNutrientRatioValid(phase: RecipePhaseForm): boolean {
    return Math.abs(nutrientRatioSum(phase) - 100) <= 0.01
  }

  function validateAllPhaseRatios(phases: RecipePhaseForm[]): boolean {
    for (const phase of phases) {
      if (!isNutrientRatioValid(phase)) {
        const label = phase.name?.trim() || `Фаза #${(phase.phase_index ?? 0) + 1}`
        showToast(`Сумма ratio должна быть 100% (${label})`, 'error', TOAST_TIMEOUT.NORMAL)
        return false
      }
    }

    return true
  }

  const onAddPhase = (): void => {
    const maxIndex = form.phases.length > 0
      ? Math.max(...form.phases.map((phase) => phase.phase_index || 0))
      : -1

    form.phases.push(createDefaultPhase(maxIndex + 1))
  }

  function buildPhasePayload(phase: RecipePhaseForm): Record<string, unknown> {
    const phMin = phase.targets.ph.min
    const phMax = phase.targets.ph.max
    const ecMin = phase.targets.ec.min
    const ecMax = phase.targets.ec.max

    return {
      phase_index: phase.phase_index,
      name: phase.name,
      duration_hours: phase.duration_hours,
      ph_target: (phMin + phMax) / 2,
      ph_min: phMin,
      ph_max: phMax,
      ec_target: (ecMin + ecMax) / 2,
      ec_min: ecMin,
      ec_max: ecMax,
      temp_air_target: toNullableNumber(phase.targets.temp_air),
      humidity_target: toNullableNumber(phase.targets.humidity_air),
      lighting_photoperiod_hours: toNullableInt(phase.targets.light_hours),
      irrigation_interval_sec: toNullableInt(phase.targets.irrigation_interval_sec),
      irrigation_duration_sec: toNullableInt(phase.targets.irrigation_duration_sec),
      nutrient_program_code: phase.nutrient_program_code?.trim() || null,
      nutrient_mode: phase.nutrient_mode || 'ratio_ec_pid',
      nutrient_npk_ratio_pct: toNullableNumber(phase.nutrient_npk_ratio_pct),
      nutrient_calcium_ratio_pct: toNullableNumber(phase.nutrient_calcium_ratio_pct),
      nutrient_magnesium_ratio_pct: toNullableNumber(phase.nutrient_magnesium_ratio_pct),
      nutrient_micro_ratio_pct: toNullableNumber(phase.nutrient_micro_ratio_pct),
      nutrient_npk_dose_ml_l: toNullableNumber(phase.nutrient_npk_dose_ml_l),
      nutrient_calcium_dose_ml_l: toNullableNumber(phase.nutrient_calcium_dose_ml_l),
      nutrient_magnesium_dose_ml_l: toNullableNumber(phase.nutrient_magnesium_dose_ml_l),
      nutrient_micro_dose_ml_l: toNullableNumber(phase.nutrient_micro_dose_ml_l),
      nutrient_npk_product_id: toNullableInt(phase.nutrient_npk_product_id),
      nutrient_calcium_product_id: toNullableInt(phase.nutrient_calcium_product_id),
      nutrient_magnesium_product_id: toNullableInt(phase.nutrient_magnesium_product_id),
      nutrient_micro_product_id: toNullableInt(phase.nutrient_micro_product_id),
      nutrient_dose_delay_sec: toNullableInt(phase.nutrient_dose_delay_sec),
      nutrient_ec_stop_tolerance: toNullableNumber(phase.nutrient_ec_stop_tolerance),
      nutrient_solution_volume_l: toNullableNumber(phase.nutrient_solution_volume_l),
    }
  }

  const onSave = async (): Promise<void> => {
    if (!form.plant_id) {
      showToast('Выберите культуру для рецепта', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    if (!validateAllPhaseRatios(form.phases)) {
      return
    }

    try {
      form.processing = true

      if (recipe.id) {
        await api.patch(`/recipes/${recipe.id}`, {
          name: form.name,
          description: form.description,
          plant_id: form.plant_id,
        })

        let draftRevisionId = recipe.draft_revision_id ?? undefined
        const hasDraft = !!draftRevisionId

        if (!draftRevisionId) {
          const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
            `/recipes/${recipe.id}/revisions`,
            { description: 'Auto draft' }
          )
          const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
          draftRevisionId = revision?.id
        }

        if (!draftRevisionId) {
          throw new Error('Draft revision ID not found')
        }

        const existingPhaseIds = hasDraft
          ? (recipe.phases || []).map((phase) => phase.id).filter((id): id is number => !!id)
          : []
        const currentPhaseIds = form.phases
          .map((phase) => phase.id)
          .filter((id): id is number => !!id)

        for (const phase of form.phases) {
          const payload = buildPhasePayload(phase)

          if (hasDraft && phase.id) {
            await api.patch(`/recipe-revision-phases/${phase.id}`, payload)
          } else {
            await api.post(`/recipe-revisions/${draftRevisionId}/phases`, payload)
          }
        }

        if (hasDraft) {
          const removedIds = existingPhaseIds.filter((id) => !currentPhaseIds.includes(id))
          for (const removedId of removedIds) {
            await api.delete(`/recipe-revision-phases/${removedId}`)
          }
        }

        await api.post(`/recipe-revisions/${draftRevisionId}/publish`)
        showToast('Рецепт успешно обновлен', 'success', TOAST_TIMEOUT.NORMAL)
        router.visit(`/recipes/${recipe.id}`)
        return
      }

      const recipeResponse = await api.post<{ data?: { id: number } }>(
        '/recipes',
        {
          name: form.name,
          description: form.description,
          plant_id: form.plant_id,
        }
      )

      const recipeId = (recipeResponse.data as { data?: { id: number } })?.data?.id

      if (!recipeId) {
        throw new Error('Recipe ID not found in response')
      }

      const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
        `/recipes/${recipeId}/revisions`,
        { description: 'Initial revision' }
      )
      const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
      const revisionId = revision?.id

      if (!revisionId) {
        throw new Error('Recipe revision ID not found in response')
      }

      for (const phase of form.phases) {
        await api.post(`/recipe-revisions/${revisionId}/phases`, buildPhasePayload(phase))
      }

      await api.post(`/recipe-revisions/${revisionId}/publish`)

      showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
      router.visit(`/recipes/${recipeId}`)
    } catch (error) {
      logger.error('Failed to save recipe:', error)
    } finally {
      form.processing = false
    }
  }

  onMounted(() => {
    void loadPlants()
    void loadNutrientProducts()
  })

  return {
    recipe,
    form,
    plants,
    plantsLoading,
    nutrientProducts,
    nutrientProductsLoading,
    npkProducts,
    calciumProducts,
    magnesiumProducts,
    microProducts,
    sortedPhases,
    nutrientRatioSum,
    isNutrientRatioValid,
    normalizePhaseRatios,
    onAddPhase,
    onSave,
  }
}
