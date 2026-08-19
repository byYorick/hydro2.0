/**
 * Harvests API client.
 *
 * Эндпоинты:
 *   POST /api/harvests — запись урожая (yield_weight_kg)
 */
import { apiPost } from './_client'

export interface CreateHarvestPayload {
  zone_id: number
  recipe_id?: number | null
  harvest_date: string
  yield_weight_kg?: number | null
  yield_count?: number | null
  quality_score?: number | null
  notes?: unknown[] | null
}

export interface HarvestRecord {
  id?: number
  zone_id: number
  recipe_id?: number | null
  harvest_date: string
  yield_weight_kg?: number | string | null
  [key: string]: unknown
}

export const harvestsApi = {
  create(payload: CreateHarvestPayload): Promise<HarvestRecord> {
    return apiPost<HarvestRecord>('/harvests', payload)
  },
}
