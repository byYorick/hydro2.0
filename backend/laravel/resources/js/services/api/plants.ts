/**
 * Plants domain API client.
 *
 * Эндпоинты:
 *   GET  /api/plants                  — все растения
 *   GET  /api/plants/with-recipe      — только с привязанным рецептом
 *   POST /api/plants/with-recipe      — создать растение вместе с рецептом
 */
import { apiGet, apiPost } from './_client'

export interface PlantRecord {
  id: number
  name: string
  [key: string]: unknown
}

export interface PlantWithRecipePayload {
  plant: {
    name: string
    species: string | null
    variety: string | null
    substrate_type: string | null
    growing_system: string | null
    photoperiod_preset: string | null
    seasonality: string | null
    description: string | null
    [key: string]: unknown
  }
  recipe: {
    name: string
    description: string | null
    revision_description: string
    phases: Array<Record<string, unknown>>
    [key: string]: unknown
  }
}

export interface PlantWithRecipeResponse {
  plant?: PlantRecord | null
  recipe?: unknown
  [key: string]: unknown
}

export interface PlantCreatePayload {
  name: string
  species?: string | null
  variety?: string | null
  [key: string]: unknown
}

export const plantsApi = {
  list(): Promise<PlantRecord[]> {
    return apiGet<PlantRecord[]>('/plants')
  },

  listWithRecipe(): Promise<PlantRecord[]> {
    return apiGet<PlantRecord[]>('/plants/with-recipe')
  },

  create(payload: PlantCreatePayload): Promise<PlantRecord> {
    return apiPost<PlantRecord>('/plants', payload)
  },

  createWithRecipe(payload: PlantWithRecipePayload): Promise<PlantWithRecipeResponse> {
    return apiPost<PlantWithRecipeResponse>('/plants/with-recipe', payload)
  },
}
