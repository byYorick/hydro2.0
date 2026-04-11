/**
 * Plant taxonomies API client.
 *
 * Эндпоинты:
 *   GET /api/plant-taxonomies          — все таксономии
 *   PUT /api/plant-taxonomies/:key     — обновить одну таксономию целиком
 */
import { apiGet, apiPut } from './_client'

export type PlantTaxonomyKey =
  | 'substrate_type'
  | 'growing_system'
  | 'photoperiod_preset'
  | 'seasonality'
  | string

export interface PlantTaxonomyItem {
  id: string
  label: string
  uses_substrate?: boolean
  [key: string]: unknown
}

export type PlantTaxonomiesResponse = Record<PlantTaxonomyKey, PlantTaxonomyItem[]>

export const plantTaxonomiesApi = {
  list(): Promise<PlantTaxonomiesResponse> {
    return apiGet<PlantTaxonomiesResponse>('/plant-taxonomies')
  },

  update(
    key: PlantTaxonomyKey,
    payload: { items: PlantTaxonomyItem[] },
  ): Promise<PlantTaxonomiesResponse> {
    return apiPut<PlantTaxonomiesResponse>(`/plant-taxonomies/${key}`, payload)
  },
}
