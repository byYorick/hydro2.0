import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import {
  ensureRecipeBinding,
  findRecipeForPlant,
  selectRecipeById,
} from '@/composables/setupWizardRecipeLinking'
import type { Recipe, SetupWizardLoadingState } from '@/composables/setupWizardTypes'

function createLoadingState(): SetupWizardLoadingState {
  return {
    greenhouses: false,
    zones: false,
    plants: false,
    recipes: false,
    nodes: false,
    stepGreenhouse: false,
    stepZone: false,
    stepPlant: false,
    stepRecipe: false,
    stepDevices: false,
    stepAutomation: false,
    stepLaunch: false,
  }
}

describe('setupWizardRecipeLinking', () => {
  it('findRecipeForPlant находит рецепт по plant_id', () => {
    const recipes: Recipe[] = [
      { id: 1, name: 'R1', plants: [{ id: 7 }] },
      { id: 2, name: 'R2', plants: [{ id: 9 }] },
    ]

    expect(findRecipeForPlant(recipes, 9)?.id).toBe(2)
    expect(findRecipeForPlant(recipes, 100)).toBeNull()
  })

  it('selectRecipeById выбирает рецепт по id', () => {
    const recipes: Recipe[] = [
      { id: 10, name: 'A' },
      { id: 11, name: 'B' },
    ]

    expect(selectRecipeById(recipes, 11)?.name).toBe('B')
    expect(selectRecipeById(recipes, null)).toBeNull()
  })

  it('ensureRecipeBinding очищает выбор при отсутствии plantId', async () => {
    const availableRecipes = ref<Recipe[]>([])
    const selectedRecipe = ref<Recipe | null>({ id: 99, name: 'Stale' })
    const selectedRecipeId = ref<number | null>(99)
    const loading = createLoadingState()

    const result = await ensureRecipeBinding({
      plantId: null,
      availableRecipes,
      selectedRecipe,
      selectedRecipeId,
      loading,
      canCreateMissing: false,
      loadRecipes: vi.fn().mockResolvedValue(undefined),
      createRecipeForPlant: vi.fn(),
    })

    expect(result).toBe('cleared_no_plant')
    expect(selectedRecipe.value).toBeNull()
    expect(selectedRecipeId.value).toBeNull()
  })

  it('ensureRecipeBinding подхватывает существующий рецепт после loadRecipes', async () => {
    const availableRecipes = ref<Recipe[]>([])
    const selectedRecipe = ref<Recipe | null>(null)
    const selectedRecipeId = ref<number | null>(null)
    const loading = createLoadingState()

    const loadRecipes = vi.fn(async () => {
      availableRecipes.value = [
        { id: 20, name: 'Found', plants: [{ id: 5 }] },
      ]
    })

    const result = await ensureRecipeBinding({
      plantId: 5,
      availableRecipes,
      selectedRecipe,
      selectedRecipeId,
      loading,
      canCreateMissing: false,
      loadRecipes,
      createRecipeForPlant: vi.fn(),
    })

    expect(result).toBe('bound_existing')
    expect(loadRecipes).toHaveBeenCalledTimes(1)
    expect(selectedRecipe.value?.id).toBe(20)
    expect(selectedRecipeId.value).toBe(20)
  })

  it('ensureRecipeBinding создает рецепт, если разрешено', async () => {
    const availableRecipes = ref<Recipe[]>([])
    const selectedRecipe = ref<Recipe | null>(null)
    const selectedRecipeId = ref<number | null>(null)
    const loading = createLoadingState()

    const createRecipeForPlant = vi.fn(async () => ({ id: 31, name: 'Created', plants: [{ id: 3 }] }))
    const loadRecipes = vi.fn().mockResolvedValue(undefined)

    const result = await ensureRecipeBinding({
      plantId: 3,
      availableRecipes,
      selectedRecipe,
      selectedRecipeId,
      loading,
      canCreateMissing: true,
      loadRecipes,
      createRecipeForPlant,
    })

    expect(result).toBe('created')
    expect(createRecipeForPlant).toHaveBeenCalledWith(3)
    expect(loadRecipes).toHaveBeenCalledTimes(2)
    expect(loading.stepRecipe).toBe(false)
    expect(selectedRecipe.value?.id).toBe(31)
    expect(selectedRecipeId.value).toBe(31)
  })

  it('ensureRecipeBinding при ошибке создания очищает stale selection', async () => {
    const availableRecipes = ref<Recipe[]>([])
    const selectedRecipe = ref<Recipe | null>({ id: 777, name: 'Old' })
    const selectedRecipeId = ref<number | null>(777)
    const loading = createLoadingState()

    const onCreateError = vi.fn()
    const result = await ensureRecipeBinding({
      plantId: 42,
      availableRecipes,
      selectedRecipe,
      selectedRecipeId,
      loading,
      canCreateMissing: true,
      loadRecipes: vi.fn().mockResolvedValue(undefined),
      createRecipeForPlant: vi.fn().mockRejectedValue(new Error('boom')),
      onCreateError,
    })

    expect(result).toBe('create_failed')
    expect(onCreateError).toHaveBeenCalledTimes(1)
    expect(loading.stepRecipe).toBe(false)
    expect(selectedRecipe.value).toBeNull()
    expect(selectedRecipeId.value).toBeNull()
  })
})
