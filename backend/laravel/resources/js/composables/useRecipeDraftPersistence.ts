import { ref } from 'vue'
import type { Recipe } from '@/types'
import type { RecipeEditorFormState, RecipePhaseFormState } from '@/composables/recipeEditorShared'
import { buildRecipePhasePayload } from '@/composables/recipeEditorShared'
import { api } from '@/services/api'

interface EnsureDraftRevisionResult { revisionId: number }

/** Owns draft IDs, clone mapping and phase CRUD; never changes an active cycle. */
export function useRecipeDraftPersistence(form: RecipeEditorFormState, initialRecipe?: Partial<Recipe> | null) {
  const recipeId = ref<number | null>(typeof initialRecipe?.id === 'number' ? initialRecipe.id : null)
  const draftRevisionId = ref<number | null>(typeof initialRecipe?.draft_revision_id === 'number' ? initialRecipe.draft_revision_id : null)
  const publishedRevisionId = ref(initialRecipe?.latest_published_revision_id ?? null)
  const sourcePhaseIndices = ref(new Map((initialRecipe?.phases ?? []).map(phase => [phase.id, phase.phase_index])))

  const initialPhaseIds = ref<number[]>(
    Array.isArray(initialRecipe?.phases)
      ? initialRecipe.phases
        .map((phase) => (typeof phase.id === 'number' ? phase.id : null))
        .filter((id): id is number => id !== null)
      : []
  )

  function resetDraft(nextRecipe?: Partial<Recipe> | null): void {
    recipeId.value = typeof nextRecipe?.id === 'number' ? nextRecipe.id : null
    draftRevisionId.value = typeof nextRecipe?.draft_revision_id === 'number' ? nextRecipe.draft_revision_id : null
    publishedRevisionId.value = nextRecipe?.latest_published_revision_id ?? null
    sourcePhaseIndices.value = new Map((nextRecipe?.phases ?? []).map(phase => [phase.id, phase.phase_index]))
    initialPhaseIds.value = Array.isArray(nextRecipe?.phases)
      ? nextRecipe.phases
        .map((phase) => (typeof phase.id === 'number' ? phase.id : null))
        .filter((id): id is number => id !== null)
      : []
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
  async function persistDraftPhases(currentRevisionId: number, phases: RecipePhaseFormState[], publish: boolean): Promise<void> {
    const persistedPhaseIds = new Set<number>()

    for (const phase of phases) {
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

    if (publish) {
      await api.recipes.publishRevision(currentRevisionId)
      publishedRevisionId.value = currentRevisionId
      draftRevisionId.value = null
      form.draft_revision_id = null
      sourcePhaseIndices.value = new Map(form.phases.flatMap(phase => typeof phase.id === 'number' ? [[phase.id, phase.phase_index] as const] : []))
    } else {
      initialPhaseIds.value = [...persistedPhaseIds]
    }

  }
  return { resetDraft, ensureRecipeShell, ensureDraftRevision, persistDraftPhases }
}
