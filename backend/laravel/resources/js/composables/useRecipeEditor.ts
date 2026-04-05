import { computed, reactive, ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { NutrientProduct, Recipe } from '@/types'
import {
  buildRecipePhasePayload,
  createDefaultRecipePhase,
  createRecipeEditorFormState,
  filterProductsByComponent,
  getRecipePhaseTargetValidationError,
  isNutrientRatioValid,
  normalizePhaseRatios,
  nutrientRatioSum,
  type PlantOption,
  type RecipeEditorFormState,
  type RecipePhaseFormState,
} from '@/composables/recipeEditorShared'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'

interface SaveRecipeOptions {
  redirectToRecipe?: boolean
}

interface EnsureDraftRevisionResult {
  revisionId: number
  createdFromClone: boolean
  clonedPhaseIds: number[]
}

export function useRecipeEditor(initialRecipe?: Partial<Recipe> | null) {
  const { showToast } = useToast()
  const { api } = useApi(showToast)

  const form = reactive<RecipeEditorFormState>(createRecipeEditorFormState(initialRecipe ?? null))
  const recipeId = ref<number | null>(typeof initialRecipe?.id === 'number' ? initialRecipe.id : null)
  const draftRevisionId = ref<number | null>(typeof initialRecipe?.draft_revision_id === 'number' ? initialRecipe.draft_revision_id : null)
  const processing = ref(false)
  const plants = ref<PlantOption[]>([])
  const plantsLoading = ref(false)
  const nutrientProducts = ref<NutrientProduct[]>([])
  const nutrientProductsLoading = ref(false)
  const initialPhaseIds = ref<number[]>(
    Array.isArray(initialRecipe?.phases)
      ? initialRecipe.phases
        .map((phase) => (typeof phase.id === 'number' ? phase.id : null))
        .filter((id): id is number => id !== null)
      : []
  )

  const npkProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'npk'))
  const calciumProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'calcium'))
  const magnesiumProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'magnesium'))
  const microProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'micro'))
  const sortedPhases = computed<RecipePhaseFormState[]>(() => {
    return [...form.phases].sort((left, right) => left.phase_index - right.phase_index)
  })

  async function loadPlants(): Promise<void> {
    try {
      plantsLoading.value = true
      const response = await api.get('/plants')
      const payload = extractData<Record<string, unknown>[]>(response.data) ?? []
      plants.value = Array.isArray(payload)
        ? payload
          .map((plant) => ({
            id: typeof plant.id === 'number' ? plant.id : 0,
            name: String(plant.name ?? ''),
          }))
          .filter((plant) => plant.id > 0 && plant.name.trim().length > 0)
        : []

      if (!form.plant_id && plants.value.length === 1) {
        form.plant_id = plants.value[0].id
      }
    } catch (error) {
      logger.error('Failed to load plants', { error })
      showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      plantsLoading.value = false
    }
  }

  async function loadNutrientProducts(): Promise<void> {
    try {
      nutrientProductsLoading.value = true
      const response = await api.get('/nutrient-products')
      const payload = extractData<Record<string, unknown>[]>(response.data) ?? []
      nutrientProducts.value = Array.isArray(payload)
        ? payload.map((item) => ({
          id: item.id as number,
          manufacturer: String(item.manufacturer ?? ''),
          name: String(item.name ?? ''),
          component: item.component as NutrientProduct['component'],
          composition: (item.composition as string | null) ?? null,
          recommended_stage: (item.recommended_stage as string | null) ?? null,
          notes: (item.notes as string | null) ?? null,
          metadata: (item.metadata as Record<string, unknown> | null) ?? null,
        }))
        : []
    } catch (error) {
      logger.error('Failed to load nutrient products', { error })
      showToast('Не удалось загрузить список удобрений', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      nutrientProductsLoading.value = false
    }
  }

  function reset(nextRecipe?: Partial<Recipe> | null): void {
    const nextForm = createRecipeEditorFormState(nextRecipe ?? null)
    form.id = nextForm.id
    form.name = nextForm.name
    form.description = nextForm.description
    form.plant_id = nextForm.plant_id
    form.draft_revision_id = nextForm.draft_revision_id
    form.phases.splice(0, form.phases.length, ...nextForm.phases)
    recipeId.value = nextForm.id
    draftRevisionId.value = nextForm.draft_revision_id
    initialPhaseIds.value = Array.isArray(nextRecipe?.phases)
      ? nextRecipe.phases
        .map((phase) => (typeof phase.id === 'number' ? phase.id : null))
        .filter((id): id is number => id !== null)
      : []
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
    if (!form.name.trim()) {
      showToast('Введите название рецепта', 'error', TOAST_TIMEOUT.NORMAL)
      return false
    }

    if (!form.plant_id) {
      showToast('Выберите культуру', 'error', TOAST_TIMEOUT.NORMAL)
      return false
    }

    if (form.phases.length === 0) {
      showToast('Добавьте хотя бы одну фазу', 'error', TOAST_TIMEOUT.NORMAL)
      return false
    }

    for (const phase of form.phases) {
      if (!phase.name.trim()) {
        showToast('У каждой фазы должно быть название', 'error', TOAST_TIMEOUT.NORMAL)
        return false
      }

      const phaseTargetError = getRecipePhaseTargetValidationError(phase)
      if (phaseTargetError) {
        const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
        showToast(`${phaseTargetError} (${label})`, 'error', TOAST_TIMEOUT.NORMAL)
        return false
      }

      if (!isNutrientRatioValid(phase)) {
        const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
        showToast(`Сумма nutrient ratio должна быть 100% (${label})`, 'error', TOAST_TIMEOUT.NORMAL)
        return false
      }
    }

    return true
  }

  async function ensureRecipeShell(): Promise<number> {
    if (recipeId.value) {
      await api.patch(`/recipes/${recipeId.value}`, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        plant_id: form.plant_id,
      })
      return recipeId.value
    }

    const response = await api.post('/recipes', {
      name: form.name.trim(),
      description: form.description.trim() || null,
      plant_id: form.plant_id,
    })

    const recipe = extractData<Record<string, unknown>>(response.data)
    const nextRecipeId = typeof recipe?.id === 'number' ? recipe.id : null
    if (!nextRecipeId) {
      throw new Error('Recipe ID missing')
    }

    recipeId.value = nextRecipeId
    form.id = nextRecipeId
    return nextRecipeId
  }

  async function ensureDraftRevision(currentRecipeId: number): Promise<EnsureDraftRevisionResult> {
    if (draftRevisionId.value) {
      return {
        revisionId: draftRevisionId.value,
        createdFromClone: false,
        clonedPhaseIds: [],
      }
    }

    const cloneFromRevisionId = typeof initialRecipe?.latest_published_revision_id === 'number'
      ? initialRecipe.latest_published_revision_id
      : null
    const response = await api.post(`/recipes/${currentRecipeId}/revisions`, {
      clone_from_revision_id: cloneFromRevisionId,
      description: recipeId.value ? 'Updated via unified editor' : 'Initial revision',
    })

    const revision = extractData<Record<string, unknown>>(response.data)
    const nextRevisionId = typeof revision?.id === 'number' ? revision.id : null
    if (!nextRevisionId) {
      throw new Error('Recipe revision ID missing')
    }

    draftRevisionId.value = nextRevisionId
    form.draft_revision_id = nextRevisionId

    const clonedPhaseIds = Array.isArray(revision?.phases)
      ? revision.phases
        .map((phase) => (typeof phase?.id === 'number' ? phase.id : null))
        .filter((phaseId): phaseId is number => phaseId !== null)
      : []

    return {
      revisionId: nextRevisionId,
      createdFromClone: cloneFromRevisionId !== null,
      clonedPhaseIds,
    }
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

      if (draftRevision.createdFromClone && draftRevision.clonedPhaseIds.length > 0) {
        for (const phaseId of draftRevision.clonedPhaseIds) {
          await api.delete(`/recipe-revision-phases/${phaseId}`)
        }

        initialPhaseIds.value = []
        form.phases.forEach((phase) => {
          delete phase.id
        })
      }

      const persistedPhaseIds = new Set<number>()

      for (const phase of sortedPhases.value) {
        const payload = buildRecipePhasePayload(phase)
        if (phase.id) {
          await api.patch(`/recipe-revision-phases/${phase.id}`, payload)
          persistedPhaseIds.add(phase.id)
        } else {
          const response = await api.post(`/recipe-revisions/${currentRevisionId}/phases`, payload)
          const createdPhase = extractData<Record<string, unknown>>(response.data)
          const phaseId = typeof createdPhase?.id === 'number' ? createdPhase.id : null
          if (phaseId) {
            phase.id = phaseId
            persistedPhaseIds.add(phaseId)
          }
        }
      }

      for (const phaseId of initialPhaseIds.value) {
        if (!persistedPhaseIds.has(phaseId)) {
          await api.delete(`/recipe-revision-phases/${phaseId}`)
        }
      }

      await api.post(`/recipe-revisions/${currentRevisionId}/publish`)
      const detailResponse = await api.get(`/recipes/${currentRecipeId}`)
      const recipe = extractData<Recipe>(detailResponse.data)
      if (!recipe?.id) {
        throw new Error('Recipe details not returned')
      }

      reset(recipe)
      showToast('Рецепт сохранён', 'success', TOAST_TIMEOUT.NORMAL)
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
    reset,
    addPhase,
    removePhase,
    saveRecipe,
    nutrientRatioSum,
    isNutrientRatioValid,
    normalizePhaseRatios,
  }
}
