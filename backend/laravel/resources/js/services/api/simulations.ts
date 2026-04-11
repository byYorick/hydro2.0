/**
 * Zone simulations API client.
 *
 * Эндпоинты:
 *   POST /api/zones/:zoneId/simulate
 *   GET  /api/simulations/:simulationId/events
 */
import { apiGet, apiPost } from './_client'

export const simulationsApi = {
  runZoneSimulation<T = unknown>(zoneId: number, payload: Record<string, unknown>): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/simulate`, payload)
  },

  getStatus<T = unknown>(jobId: string): Promise<T> {
    return apiGet<T>(`/simulations/${jobId}`)
  },

  listEvents<T = unknown>(
    simulationId: number,
    params?: { order?: 'asc' | 'desc'; limit?: number; [key: string]: unknown },
  ): Promise<T> {
    return apiGet<T>(`/simulations/${simulationId}/events`, { params })
  },
}
