import { computed, reactive, ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { api } from '@/services/api'
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
import { logger } from '@/utils/logger'

interface SaveRecipeOptions {
  redirectToRecipe?: boolean
  publish?: boolean
}

interface EnsureDraftRevisionResult {
  revisionId: number
}

export function useRecipeEditor(initialRecipe?: Partial<Recipe> | null) {
  const { showToast } = useToast()

  const form = reactive<RecipeEditorFormState>(createRecipeEditorFormState(initialRecipe ?? null))
  const recipeId = ref<number | null>(typeof initialRecipe?.id === 'number' ? initialRecipe.id : null)
  const draftRevisionId = ref<number | null>(typeof initialRecipe?.draft_revision_id === 'number' ? initialRecipe.draft_revision_id : null)
  const publishedRevisionId = ref(initialRecipe?.latest_published_revision_id ?? null)
  const sourcePhaseIndices = ref(new Map((initialRecipe?.phases ?? []).map(phase => [phase.id, phase.phase_index])))
  const processing = ref(false)
  const plants = ref<PlantOption[]>([])
  const plantsLoading = ref(false)
  const nutrientProducts = ref<NutrientProduct[]>([])
  const nutrientProductsLoading = ref(false)
  const substrates = ref<import('@/services/api/substrates').Substrate[]>([])
  const substratesLoading = ref(false)
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
      const payload = await api.plants.list()
      plants.value = payload
        .map((plant) => ({
          id: typeof plant.id === 'number' ? plant.id : 0,
          name: String(plant.name ?? ''),
        }))
        .filter((plant) => plant.id > 0 && plant.name.trim().length > 0)

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
      nutrientProducts.value = await api.nutrientProducts.list()
    } catch (error) {
      logger.error('Failed to load nutrient products', { error })
      showToast('Не удалось загрузить список удобрений', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      nutrientProductsLoading.value = false
    }
  }

  async function loadSubstrates(): Promise<void> {
    try {
      substratesLoading.value = true
      substrates.value = await api.substrates.list()
    } catch (error) {
      logger.error('Failed to load substrates', { error })
      showToast('Не удалось загрузить список субстратов', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      substratesLoading.value = false
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
    publishedRevisionId.value = nextRecipe?.latest_published_revision_id ?? null
    sourcePhaseIndices.value = new Map((nextRecipe?.phases ?? []).map(phase => [phase.id, phase.phase_index]))
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

      const ratioMode = phase.nutrient_mode === 'ratio_ec_pid' || phase.nutrient_mode === 'delta_ec_by_k'
      const hasEcTarget = (phase.ec_target ?? 0) > 0
      const hasAllRatios = phase.nutrient_npk_ratio_pct != null
        && phase.nutrient_calcium_ratio_pct != null
        && phase.nutrient_magnesium_ratio_pct != null
        && phase.nutrient_micro_ratio_pct != null
      if (ratioMode && hasEcTarget && !hasAllRatios) {
        const label = phase.name.trim() || `Фаза ${phase.phase_index + 1}`
        showToast(`Для режима ${phase.nutrient_mode} при EC > 0 обязательны все 4 доли компонентов (${label})`, 'error', TOAST_TIMEOUT.NORMAL)
        return false
      }
    }

    return true
  }

  async function ensureRecipeShell(): Promise<number> {
    const shellPayload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      plant_id: form.plant_id,
    }

    if (recipeId.value) {
      await api.recipes.update(recipeId.value, shellPayload)
      return recipeId.value
    }

    const recipe = await api.recipes.create(shellPayload)
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
      }
    }

    const cloneFromRevisionId = publishedRevisionId.value
    const revision = await api.recipes.createRevision(currentRecipeId, {
      clone_from_revision_id: cloneFromRevisionId,
      description: recipeId.value ? 'Updated via unified editor' : 'Initial revision',
    })

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

    // Keep cloned phases (and their steps) attached to the corresponding source phase.
    // Published phase IDs must never be used for draft updates or deletion.
    const clonedByIndex = new Map((revision.phases ?? []).map(phase => [phase.phase_index, phase.id]))
    for (const phase of form.phases) {
      const sourceIndex = phase.id == null ? undefined : sourcePhaseIndices.value.get(phase.id)
      const clonedId = sourceIndex == null ? undefined : clonedByIndex.get(sourceIndex)
      if (typeof clonedId === 'number') phase.id = clonedId
      else delete phase.id
    }
    initialPhaseIds.value = clonedPhaseIds
    return { revisionId: nextRevisionId }
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

      const persistedPhaseIds = new Set<number>()

      for (const phase of sortedPhases.value) {
        const payload = buildRecipePhasePayload(phase)
        if (phase.id) {
          await api.recipes.updatePhase(phase.id, payload)
          persistedPhaseIds.add(phase.id)
        } else {
          const createdPhase = await api.recipes.createPhase(currentRevisionId, payload)
          const phaseId = typeof createdPhase?.id === 'number' ? createdPhase.id : null
          if (phaseId) {
            phase.id = phaseId
            persistedPhaseIds.add(phaseId)
          }
        }
      }

      for (const phaseId of initialPhaseIds.value) {
        if (!persistedPhaseIds.has(phaseId)) {
          await api.recipes.deletePhase(phaseId)
        }
      }

      if (options.publish) {
        await api.recipes.publishRevision(currentRevisionId)
        publishedRevisionId.value = currentRevisionId
        draftRevisionId.value = null
        form.draft_revision_id = null
        sourcePhaseIndices.value = new Map(form.phases.flatMap(phase => typeof phase.id === 'number' ? [[phase.id, phase.phase_index] as const] : []))
      } else {
        initialPhaseIds.value = [...persistedPhaseIds]
      }
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
