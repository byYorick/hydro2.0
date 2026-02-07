import type { Ref } from 'vue'
import type { Recipe, SetupWizardLoadingState } from './setupWizardTypes'

export type EnsureRecipeBindingResult =
  | 'cleared_no_plant'
  | 'bound_existing'
  | 'cleared_missing'
  | 'created'
  | 'create_failed'

export interface EnsureRecipeBindingOptions {
  plantId: number | null
  availableRecipes: Ref<Recipe[]>
  selectedRecipe: Ref<Recipe | null>
  selectedRecipeId: Ref<number | null>
  loading: SetupWizardLoadingState
  canCreateMissing: boolean
  loadRecipes: () => Promise<void>
  createRecipeForPlant: (plantId: number) => Promise<Recipe>
  onCreateError?: (error: unknown) => void
}

export function recipeMatchesPlant(recipe: Recipe, plantId: number): boolean {
  return Array.isArray(recipe.plants) && recipe.plants.some((plant) => plant.id === plantId)
}

export function findRecipeForPlant(recipes: Recipe[], plantId: number): Recipe | null {
  return recipes.find((recipe) => recipeMatchesPlant(recipe, plantId)) ?? null
}

export function selectRecipeById(recipes: Recipe[], recipeId: number | null): Recipe | null {
  if (!recipeId) {
    return null
  }

  return recipes.find((recipe) => recipe.id === recipeId) ?? null
}

function clearSelectedRecipe(selectedRecipe: Ref<Recipe | null>, selectedRecipeId: Ref<number | null>): void {
  selectedRecipe.value = null
  selectedRecipeId.value = null
}

function bindRecipe(selectedRecipe: Ref<Recipe | null>, selectedRecipeId: Ref<number | null>, recipe: Recipe): void {
  selectedRecipe.value = recipe
  selectedRecipeId.value = recipe.id
}

export async function ensureRecipeBinding(options: EnsureRecipeBindingOptions): Promise<EnsureRecipeBindingResult> {
  const {
    plantId,
    availableRecipes,
    selectedRecipe,
    selectedRecipeId,
    loading,
    canCreateMissing,
    loadRecipes,
    createRecipeForPlant,
    onCreateError,
  } = options

  if (!plantId) {
    clearSelectedRecipe(selectedRecipe, selectedRecipeId)
    return 'cleared_no_plant'
  }

  let existingRecipe = findRecipeForPlant(availableRecipes.value, plantId)
  if (!existingRecipe && !loading.recipes) {
    await loadRecipes()
    existingRecipe = findRecipeForPlant(availableRecipes.value, plantId)
  }

  if (existingRecipe) {
    bindRecipe(selectedRecipe, selectedRecipeId, existingRecipe)
    return 'bound_existing'
  }

  if (!canCreateMissing) {
    clearSelectedRecipe(selectedRecipe, selectedRecipeId)
    return 'cleared_missing'
  }

  loading.stepRecipe = true
  try {
    const recipe = await createRecipeForPlant(plantId)
    bindRecipe(selectedRecipe, selectedRecipeId, recipe)
    await loadRecipes()
    return 'created'
  } catch (error) {
    clearSelectedRecipe(selectedRecipe, selectedRecipeId)
    onCreateError?.(error)
    return 'create_failed'
  } finally {
    loading.stepRecipe = false
  }
}
