import { computed, reactive, ref, toRef } from 'vue'
import { router } from '@inertiajs/vue3'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Recipe } from '@/types'
import { createDefaultRecipePhase, createRecipeEditorFormState, isNutrientRatioValid, normalizePhaseRatios, nutrientRatioSum, type RecipeEditorFormState, type RecipePhaseFormState } from '@/composables/recipeEditorShared'
import { useRecipeCatalogs } from '@/composables/useRecipeCatalogs'
import { useRecipeDraftPersistence } from '@/composables/useRecipeDraftPersistence'
import { recipeEditorValidationError } from '@/composables/recipeEditorValidation'
import { logger } from '@/utils/logger'

interface SaveRecipeOptions { redirectToRecipe?: boolean; publish?: boolean }

export function useRecipeEditor(initialRecipe?: Partial<Recipe> | null) {
  const { showToast } = useToast()
  const form = reactive<RecipeEditorFormState>(createRecipeEditorFormState(initialRecipe ?? null))
  const processing = ref(false)
  const { resetDraft, ensureRecipeShell, ensureDraftRevision, persistDraftPhases } = useRecipeDraftPersistence(form, initialRecipe)
  const { plants, plantsLoading, nutrientProducts, nutrientProductsLoading, npkProducts, calciumProducts, magnesiumProducts, microProducts, substrates, substratesLoading, loadPlants, loadNutrientProducts, loadSubstrates } = useRecipeCatalogs(toRef(form, 'plant_id'))
const sortedPhases = computed<RecipePhaseFormState[]>(() => {
    return [...form.phases].sort((left, right) => left.phase_index - right.phase_index)
  })
  function reset(nextRecipe?: Partial<Recipe> | null): void {
    const nextForm = createRecipeEditorFormState(nextRecipe ?? null)
    form.id = nextForm.id
    form.name = nextForm.name
    form.description = nextForm.description
    form.plant_id = nextForm.plant_id
    form.draft_revision_id = nextForm.draft_revision_id
    form.phases.splice(0, form.phases.length, ...nextForm.phases)
    resetDraft(nextRecipe)
  }
  function addPhase(): void {
    const maxIndex = form.phases.length > 0
      ? Math.max(...form.phases.map((phase) => phase.phase_index))
      : -1
    form.phases.push(createDefaultRecipePhase(maxIndex + 1))
  }
  function removePhase(index: number): void {
    if (form.phases.length <= 1) {
      return
    }

    form.phases.splice(index, 1)
    form.phases.forEach((phase, phaseIndex) => {
      phase.phase_index = phaseIndex
    })
  }
  function validate(): boolean {
    const error = recipeEditorValidationError(form)
    if (error) showToast(error, 'error', TOAST_TIMEOUT.NORMAL)
    return error === null
  }
  async function saveRecipe(options: SaveRecipeOptions = {}): Promise<Recipe | null> {
    if (processing.value) {
      return null
    }

    if (!validate()) {
      return null
    }

    processing.value = true
    try {
      const currentRecipeId = await ensureRecipeShell()
      const draftRevision = await ensureDraftRevision(currentRecipeId)
      const currentRevisionId = draftRevision.revisionId

      await persistDraftPhases(currentRevisionId, sortedPhases.value, Boolean(options.publish))
      const recipe = await api.recipes.getById(currentRecipeId)
      if (!recipe?.id) {
        throw new Error('Recipe details not returned')
      }

      reset(recipe)
      showToast(options.publish ? 'Ревизия опубликована. Активные циклы не переключены.' : 'Черновик сохранён', 'success', TOAST_TIMEOUT.NORMAL)
      if (options.redirectToRecipe) {
        router.visit(`/recipes/${recipe.id}`)
      }
      return recipe
    } catch (error) {
      logger.error('Failed to save recipe', { error })
      showToast('Не удалось сохранить рецепт', 'error', TOAST_TIMEOUT.NORMAL)
      return null
    } finally {
      processing.value = false
    }
  }
  return {
    form,
    processing,
    plants,
    plantsLoading,
    nutrientProducts,
    nutrientProductsLoading,
    npkProducts,
    calciumProducts,
    magnesiumProducts,
    microProducts,
    sortedPhases,
    loadPlants,
    loadNutrientProducts,
    substrates,
    substratesLoading,
    loadSubstrates,
    reset,
    addPhase,
    removePhase,
    saveRecipe,
    validate,
    nutrientRatioSum,
    isNutrientRatioValid,
    normalizePhaseRatios,
  }
}
