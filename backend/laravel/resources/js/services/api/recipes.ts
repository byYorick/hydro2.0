/**
 * Recipes domain API client.
 *
 * Эндпоинты:
 *   POST   /api/recipes
 *   PATCH  /api/recipes/:id
 *   GET    /api/recipes/:id
 *   POST   /api/recipes/:id/revisions
 *   POST   /api/recipe-revisions/:id/publish
 *   POST   /api/recipe-revisions/:id/phases
 *   PATCH  /api/recipe-revision-phases/:id
 *   DELETE /api/recipe-revision-phases/:id
 */
import type { Recipe } from '@/types'
import { apiGet, apiPost, apiPostVoid, apiPatch, apiPatchVoid, apiPut, apiDelete } from './_client'

export interface PaginatedRecipesEnvelope {
  data: Recipe[]
  current_page?: number | null
  last_page?: number | null
  total?: number | null
  [key: string]: unknown
}

export interface RecipeShellPayload {
  name: string
  description: string | null
  plant_id: number | null
}

export interface RecipeRevisionPayload {
  clone_from_revision_id: number | null
  description: string
}

export interface RecipeRevisionRecord {
  id: number
  phases?: Array<{ id?: number | null } & Record<string, unknown>>
  [key: string]: unknown
}

export interface RecipesListParams {
  search?: string
  [key: string]: string | number | boolean | undefined
}

export const recipesApi = {
  list(params?: RecipesListParams): Promise<Recipe[]> {
    return apiGet<Recipe[]>('/recipes', { params })
  },

  /**
   * Постраничная версия — возвращает envelope с `current_page`/`last_page`.
   * `extractData` обновлён так, что пагинированные envelope'ы больше не
   * разворачиваются, поэтому достаточно стандартного `apiGet`.
   */
  listPaginated(params?: RecipesListParams): Promise<PaginatedRecipesEnvelope> {
    return apiGet<PaginatedRecipesEnvelope>('/recipes', { params })
  },

  getById(recipeId: number): Promise<Recipe> {
    return apiGet<Recipe>(`/recipes/${recipeId}`)
  },

  create(payload: RecipeShellPayload): Promise<Recipe> {
    return apiPost<Recipe>('/recipes', payload)
  },

  update(recipeId: number, payload: RecipeShellPayload): Promise<void> {
    return apiPatchVoid(`/recipes/${recipeId}`, payload)
  },

  /**
   * Partial update, возвращающий сам Recipe (для admin-форм, где нужно
   * обновить локальный store после patch).
   */
  updateFields(recipeId: number, payload: Partial<RecipeShellPayload>): Promise<Recipe> {
    return apiPatch<Recipe>(`/recipes/${recipeId}`, payload)
  },

  getRevision(revisionId: number): Promise<RecipeRevisionRecord> {
    return apiGet<RecipeRevisionRecord>(`/recipe-revisions/${revisionId}`)
  },

  createRevision(recipeId: number, payload: RecipeRevisionPayload): Promise<RecipeRevisionRecord> {
    return apiPost<RecipeRevisionRecord>(`/recipes/${recipeId}/revisions`, payload)
  },

  publishRevision(revisionId: number): Promise<void> {
    return apiPostVoid(`/recipe-revisions/${revisionId}/publish`)
  },

  createPhase(revisionId: number, payload: Record<string, unknown>): Promise<{ id: number } & Record<string, unknown>> {
    return apiPost<{ id: number } & Record<string, unknown>>(`/recipe-revisions/${revisionId}/phases`, payload)
  },

  updatePhase(phaseId: number, payload: Record<string, unknown>): Promise<void> {
    return apiPatchVoid(`/recipe-revision-phases/${phaseId}`, payload)
  },

  deletePhase(phaseId: number): Promise<void> {
    return apiDelete<void>(`/recipe-revision-phases/${phaseId}`)
  },

  analytics<T = unknown>(recipeId: number, params?: Record<string, unknown>): Promise<T> {
    return apiGet<T>(`/recipes/${recipeId}/analytics`, { params })
  },

  comparison<T = unknown>(payload: { recipe_ids: number[] }): Promise<T> {
    return apiPost<T>('/recipes/comparison', payload)
  },

  getStageMap(recipeId: number): Promise<{ stage_map?: Array<{ phase_index: number; stage: string }> }> {
    return apiGet<{ stage_map?: Array<{ phase_index: number; stage: string }> }>(
      `/recipes/${recipeId}/stage-map`,
    )
  },

  updateStageMap(
    recipeId: number,
    payload: { stage_map: Array<{ phase_index: number; stage: string }> },
  ): Promise<unknown> {
    return apiPut<unknown>(`/recipes/${recipeId}/stage-map`, payload)
  },

  /**
   * Активные grow-cycle, использующие этот рецепт. Используется для UI-warning
   * "Recipe used in active cycle — изменения применятся только после revision switch".
   */
  getActiveUsage(recipeId: number): Promise<RecipeActiveUsage> {
    return apiGet<RecipeActiveUsage>(`/recipes/${recipeId}/active-usage`)
  },
}

export interface RecipeActiveUsageItem {
  cycle_id: number
  zone_id: number
  zone_name: string | null
  revision_id: number
  revision_number: number | null
  status: string
  started_at: string | null
}

export interface RecipeActiveUsage {
  recipe_id: number
  active_cycles: RecipeActiveUsageItem[]
  count: number
}
