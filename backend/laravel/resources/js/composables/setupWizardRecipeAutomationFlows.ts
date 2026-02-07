import type { ComputedRef, Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import { extractData } from '@/utils/apiHelpers'
import type {
  AutomationFormState,
  Plant,
  Recipe,
  RecipePhase,
  RecipeFormState,
  SetupWizardLoadingState,
  Zone,
} from './setupWizardTypes'
import {
  addRecipePhase as appendRecipePhase,
  createRecipeForPlant,
  type SetupWizardRecipeApiClient,
} from './setupWizardRecipeCreation'
import {
  ensureRecipeBinding,
  selectRecipeById,
} from './setupWizardRecipeLinking'

interface SetupWizardRecipeAutomationFlowsOptions {
  api: SetupWizardRecipeApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  recipeForm: RecipeFormState
  availableRecipes: Ref<Recipe[]>
  selectedPlant: Ref<Plant | null>
  selectedPlantId: Ref<number | null>
  selectedRecipeId: Ref<number | null>
  selectedRecipe: Ref<Recipe | null>
  automationForm: AutomationFormState
  selectedZone: Ref<Zone | null>
  automationAppliedAt: Ref<string | null>
  loadRecipes: () => Promise<void>
  visit: (url: string) => void
}

function toNumberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  return null
}

function resolveSystemTypeFromPhase(phase: RecipePhase | undefined, current: AutomationFormState['systemType']): AutomationFormState['systemType'] {
  const rawMode = phase?.irrigation_mode?.toString().toUpperCase() ?? ''
  if (rawMode === 'SUBSTRATE') {
    return 'substrate_trays'
  }
  if (rawMode === 'RECIRC') {
    return 'nft'
  }

  return current
}

function pickPrimaryPhase(recipe: Recipe | null): RecipePhase | null {
  if (!recipe || !Array.isArray(recipe.phases) || recipe.phases.length === 0) {
    return null
  }

  return [...recipe.phases].sort((a, b) => a.phase_index - b.phase_index)[0] ?? null
}

function buildGrowthCycleConfigPayload(automationForm: AutomationFormState) {
  const tanksCount = automationForm.systemType === 'drip' ? 2 : 3

  return {
    mode: 'adjust' as const,
    subsystems: {
      ph: {
        enabled: true,
        targets: {
          min: Number((automationForm.targetPh - 0.2).toFixed(2)),
          max: Number((automationForm.targetPh + 0.2).toFixed(2)),
          target: Number(automationForm.targetPh.toFixed(2)),
        },
      },
      ec: {
        enabled: true,
        targets: {
          min: Number((automationForm.targetEc - 0.2).toFixed(2)),
          max: Number((automationForm.targetEc + 0.2).toFixed(2)),
          target: Number(automationForm.targetEc.toFixed(2)),
        },
      },
      irrigation: {
        enabled: true,
        targets: {
          interval_minutes: automationForm.intervalMinutes,
          duration_seconds: automationForm.durationSeconds,
          system_type: automationForm.systemType,
          tanks_count: tanksCount,
          clean_tank_fill_l: automationForm.cleanTankFillL,
          nutrient_tank_target_l: automationForm.nutrientTankFillL,
          fill_strategy: 'volume',
          correction_strategy: 'feedback_target',
          drain_control: {
            enabled: tanksCount === 3,
            target_percent: tanksCount === 3 ? automationForm.drainTargetPercent : 0,
          },
          correction_node: {
            target_ph: Number(automationForm.targetPh.toFixed(2)),
            target_ec: Number(automationForm.targetEc.toFixed(2)),
            sensors_location: 'correction_node',
          },
        },
      },
      climate: {
        enabled: automationForm.manageClimate,
        targets: {
          temperature: automationForm.dayTemp,
          humidity: automationForm.dayHumidity,
          vent_control: {
            min_open_percent: automationForm.ventMinPercent,
            max_open_percent: automationForm.ventMaxPercent,
          },
          external_guard: {
            enabled: true,
          },
        },
      },
      lighting: {
        enabled: automationForm.manageLighting,
        targets: {
          lux_target_day: automationForm.luxDay,
          future_metrics: {
            ppfd: null,
            dli: null,
          },
        },
      },
    },
  }
}

export function createSetupWizardRecipeAutomationFlows(options: SetupWizardRecipeAutomationFlowsOptions) {
  const {
    api,
    loading,
    canConfigure,
    showToast,
    recipeForm,
    availableRecipes,
    selectedPlant,
    selectedPlantId,
    selectedRecipeId,
    selectedRecipe,
    automationForm,
    selectedZone,
    automationAppliedAt,
    loadRecipes,
    visit,
  } = options

  function addRecipePhase(): void {
    appendRecipePhase(recipeForm)
  }

  function syncAutomationFromRecipe(recipe: Recipe | null): void {
    const phase = pickPrimaryPhase(recipe)
    if (!phase) {
      return
    }

    const systemType = resolveSystemTypeFromPhase(phase, automationForm.systemType)
    const phTarget = toNumberOrNull(phase.ph_target)
    const ecTarget = toNumberOrNull(phase.ec_target)
    const tempAirTarget = toNumberOrNull(phase.extensions?.day_night?.temperature?.day ?? phase.temp_air_target)
    const humidityTarget = toNumberOrNull(phase.extensions?.day_night?.humidity?.day ?? phase.humidity_target)
    const photoperiod = toNumberOrNull(phase.lighting_photoperiod_hours)
    const irrigationIntervalSec = toNumberOrNull(phase.irrigation_interval_sec)
    const irrigationDurationSec = toNumberOrNull(phase.irrigation_duration_sec)

    automationForm.systemType = systemType
    if (phTarget !== null) {
      automationForm.targetPh = Number(phTarget.toFixed(2))
    }
    if (ecTarget !== null) {
      automationForm.targetEc = Number(ecTarget.toFixed(2))
    }
    if (tempAirTarget !== null) {
      automationForm.dayTemp = Number(tempAirTarget.toFixed(1))
    }
    if (humidityTarget !== null) {
      automationForm.dayHumidity = Math.round(humidityTarget)
    }
    if (photoperiod !== null) {
      automationForm.luxDay = Math.max(4000, photoperiod * 1000)
    }
    if (irrigationIntervalSec !== null && irrigationIntervalSec > 0) {
      automationForm.intervalMinutes = Math.max(1, Math.round(irrigationIntervalSec / 60))
    }
    if (irrigationDurationSec !== null && irrigationDurationSec > 0) {
      automationForm.durationSeconds = Math.round(irrigationDurationSec)
    }
  }

  async function loadRecipeDetails(recipeId: number | null): Promise<Recipe | null> {
    if (!recipeId) {
      return null
    }

    try {
      const response = await api.get(`/recipes/${recipeId}`)
      const recipe = extractData<Recipe>(response.data)
      if (!recipe?.id) {
        return null
      }

      const index = availableRecipes.value.findIndex((item) => item.id === recipe.id)
      if (index >= 0) {
        availableRecipes.value[index] = recipe
      } else {
        availableRecipes.value.push(recipe)
      }

      return recipe
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load recipe details', { error, recipeId })
      return null
    }
  }

  async function ensureRecipeForPlant(createIfMissing = false): Promise<void> {
    const result = await ensureRecipeBinding({
      plantId: selectedPlantId.value,
      availableRecipes,
      selectedRecipe,
      selectedRecipeId,
      loading,
      canCreateMissing: createIfMissing && canConfigure.value,
      loadRecipes,
      createRecipeForPlant: (plantId) => createRecipeForPlant({
        api,
        canConfigure: canConfigure.value,
        recipeForm,
        plantId,
        plantName: selectedPlant.value?.name,
      }),
      onCreateError: (error) => {
        logger.error('[Setup/Wizard] Failed to ensure recipe for plant', { error })
      },
    })

    if (result === 'created') {
      showToast('Рецепт для выбранной культуры создан и привязан', 'success', TOAST_TIMEOUT.NORMAL)
    }
  }

  async function createRecipe(): Promise<void> {
    if (!selectedPlantId.value) {
      showToast('Сначала выберите растение на шаге 3', 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    await ensureRecipeForPlant(true)
  }

  function selectRecipe(): void {
    if (!canConfigure.value) {
      return
    }

    const recipe = selectRecipeById(availableRecipes.value, selectedRecipeId.value)
    if (!recipe) {
      return
    }

    selectedRecipe.value = recipe
    syncAutomationFromRecipe(recipe)
    showToast('Рецепт выбран', 'success', TOAST_TIMEOUT.NORMAL)
  }

  async function applyAutomation(): Promise<void> {
    if (!canConfigure.value || !selectedZone.value?.id) {
      return
    }

    if (!selectedRecipe.value?.id) {
      showToast('Сначала выберите культуру с рецептом, чтобы подтянуть параметры автоматики', 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    syncAutomationFromRecipe(selectedRecipe.value)

    if (automationForm.ventMinPercent > automationForm.ventMaxPercent) {
      showToast('Минимальное открытие форточки не может быть больше максимального', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }

    loading.stepAutomation = true
    try {
      await api.post(`/zones/${selectedZone.value.id}/commands`, {
        type: 'GROWTH_CYCLE_CONFIG',
        params: buildGrowthCycleConfigPayload(automationForm),
      })

      automationAppliedAt.value = new Date().toISOString()
      showToast('Логика автоматики применена', 'success', TOAST_TIMEOUT.NORMAL)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to apply automation profile', { error })
    } finally {
      loading.stepAutomation = false
    }
  }

  async function openCycleWizard(): Promise<void> {
    await ensureRecipeForPlant(false)

    if (!selectedZone.value?.id || !selectedRecipe.value?.id) {
      showToast('Не найден рецепт для выбранной культуры. Создайте культуру или рецепт.', 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    loading.stepLaunch = true
    try {
      const url = `/zones/${selectedZone.value.id}?start_cycle=1&recipe_id=${selectedRecipe.value.id}`
      showToast('Открываю мастер запуска цикла', 'info', TOAST_TIMEOUT.NORMAL)
      visit(url)
    } finally {
      loading.stepLaunch = false
    }
  }

  return {
    addRecipePhase,
    createRecipe,
    selectRecipe,
    ensureRecipeForPlant,
    applyAutomation,
    openCycleWizard,
    syncAutomationFromRecipe,
    loadRecipeDetails,
  }
}
