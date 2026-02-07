import { extractData } from '@/utils/apiHelpers'
import type { Recipe, RecipeFormState } from './setupWizardTypes'

export interface SetupWizardRecipeApiClient {
  get(url: string, config?: unknown): Promise<{ data: unknown }>
  post(url: string, data?: unknown, config?: unknown): Promise<{ data: unknown }>
}

interface CreateRecipeForPlantOptions {
  api: SetupWizardRecipeApiClient
  canConfigure: boolean
  recipeForm: RecipeFormState
  plantId: number
  plantName?: string | null
}

export function buildAutoRecipeName(plantName: string | null | undefined, fallbackRecipeName: string): string {
  const normalizedPlantName = plantName?.trim()
  if (normalizedPlantName) {
    return `${normalizedPlantName} — базовый рецепт`
  }

  const normalizedFallback = fallbackRecipeName.trim()
  return normalizedFallback || 'Базовый рецепт'
}

export function addRecipePhase(recipeForm: RecipeFormState): void {
  const maxIndex = recipeForm.phases.length > 0
    ? Math.max(...recipeForm.phases.map((phase) => phase.phase_index))
    : -1

  recipeForm.phases.push({
    phase_index: maxIndex + 1,
    name: `Фаза ${maxIndex + 2}`,
    duration_hours: 72,
    targets: {
      ph: 5.8,
      ec: 1.6,
      temp_air: 23,
      humidity_air: 62,
      light_hours: 16,
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 15,
    },
  })
}

export async function createRecipeForPlant(options: CreateRecipeForPlantOptions): Promise<Recipe> {
  const {
    api,
    canConfigure,
    recipeForm,
    plantId,
    plantName,
  } = options

  if (!canConfigure) {
    throw new Error('Недостаточно прав для создания рецепта')
  }

  const recipeName = buildAutoRecipeName(plantName, recipeForm.name)
  if (!recipeName) {
    throw new Error('Не указано название рецепта')
  }

  const recipeResponse = await api.post('/recipes', {
    name: recipeName,
    description: recipeForm.description,
    plant_id: plantId,
  })

  const recipePayload = extractData<Record<string, unknown>>(recipeResponse.data)
  const recipeId = typeof recipePayload?.id === 'number' ? recipePayload.id : null
  if (!recipeId) {
    throw new Error('Recipe ID missing')
  }

  const revisionResponse = await api.post(`/recipes/${recipeId}/revisions`, {
    description: 'Initial revision from setup wizard',
  })

  const revisionPayload = extractData<Record<string, unknown>>(revisionResponse.data)
  const revisionId = typeof revisionPayload?.id === 'number' ? revisionPayload.id : null
  if (!revisionId) {
    throw new Error('Recipe revision ID missing')
  }

  for (const phase of recipeForm.phases) {
    await api.post(`/recipe-revisions/${revisionId}/phases`, {
      phase_index: phase.phase_index,
      name: phase.name || `Фаза ${phase.phase_index + 1}`,
      duration_hours: phase.duration_hours,
      ph_target: phase.targets.ph,
      ph_min: phase.targets.ph,
      ph_max: phase.targets.ph,
      ec_target: phase.targets.ec,
      ec_min: phase.targets.ec,
      ec_max: phase.targets.ec,
      temp_air_target: phase.targets.temp_air,
      humidity_target: phase.targets.humidity_air,
      lighting_photoperiod_hours: phase.targets.light_hours,
      irrigation_interval_sec: phase.targets.irrigation_interval_sec,
      irrigation_duration_sec: phase.targets.irrigation_duration_sec,
    })
  }

  await api.post(`/recipe-revisions/${revisionId}/publish`)

  const recipeDetailsResponse = await api.get(`/recipes/${recipeId}`)
  const recipe = extractData<Recipe>(recipeDetailsResponse.data)
  if (!recipe?.id) {
    throw new Error('Recipe details not returned')
  }

  return recipe
}
