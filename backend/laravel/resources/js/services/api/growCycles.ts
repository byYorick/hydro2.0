/**
 * Grow cycles API client.
 *
 * Эндпоинты:
 *   POST /api/grow-cycles/:id/pause
 *   POST /api/grow-cycles/:id/resume
 *   POST /api/grow-cycles/:id/advance-phase
 *   POST /api/grow-cycles/:id/harvest
 *   POST /api/grow-cycles/:id/abort
 *   POST /api/grow-cycles/:id/change-recipe-revision
 */
import { apiPostVoid } from './_client'

export interface HarvestPayload {
  batch_label?: string | null
}

export interface AbortPayload {
  notes?: string | null
}

export interface ChangeRecipeRevisionPayload {
  recipe_revision_id: number
  apply_mode: 'now' | 'next_phase'
}

export const growCyclesApi = {
  pause(cycleId: number): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/pause`, {})
  },

  resume(cycleId: number): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/resume`, {})
  },

  advancePhase(cycleId: number): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/advance-phase`, {})
  },

  harvest(cycleId: number, payload: HarvestPayload = {}): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/harvest`, payload)
  },

  abort(cycleId: number, payload: AbortPayload = {}): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/abort`, payload)
  },

  changeRecipeRevision(cycleId: number, payload: ChangeRecipeRevisionPayload): Promise<void> {
    return apiPostVoid(`/grow-cycles/${cycleId}/change-recipe-revision`, payload)
  },
}
