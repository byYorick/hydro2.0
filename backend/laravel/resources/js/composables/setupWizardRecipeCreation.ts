import { api } from '@/services/api'
import { buildRecipePhasePayload, createDefaultRecipePhase, mapSimpleRecipePhaseToForm } from '@/composables/recipeEditorShared'
import type { Recipe, RecipeFormState } from './setupWizardTypes'

interface CreateRecipeForPlantOptions {
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

  const phase = createDefaultRecipePhase(maxIndex + 1)
  recipeForm.phases.push({
    phase_index: phase.phase_index,
    name: phase.name,
    duration_hours: phase.duration_hours,
    targets: {
      ph: phase.ph_min,
      ec: phase.ec_min,
      temp_air: phase.temp_air_target ?? 23,
      humidity_air: phase.humidity_target ?? 62,
      light_hours: phase.lighting_photoperiod_hours ?? 16,
      irrigation_interval_sec: phase.irrigation_interval_sec ?? 900,
      irrigation_duration_sec: phase.irrigation_duration_sec ?? 15,
    },
  })
}

export async function createRecipeForPlant(options: CreateRecipeForPlantOptions): Promise<Recipe> {
  const {
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

  const recipePayload = await api.recipes.create({
    name: recipeName,
    description: recipeForm.description,
    plant_id: plantId,
  })

  const recipeId = typeof recipePayload?.id === 'number' ? recipePayload.id : null
  if (!recipeId) {
    throw new Error('Recipe ID missing')
  }

  const revisionPayload = await api.recipes.createRevision(recipeId, {
    clone_from_revision_id: null,
    description: 'Initial revision from setup wizard',
  })

  const revisionId = typeof revisionPayload?.id === 'number' ? revisionPayload.id : null
  if (!revisionId) {
    throw new Error('Recipe revision ID missing')
  }

  for (const phase of recipeForm.phases) {
    await api.recipes.createPhase(
      revisionId,
      buildRecipePhasePayload(mapSimpleRecipePhaseToForm(phase)),
    )
  }

  await api.recipes.publishRevision(revisionId)

  const recipe = await api.recipes.getById(recipeId)
  if (!recipe?.id) {
    throw new Error('Recipe details not returned')
  }

  return recipe
}
