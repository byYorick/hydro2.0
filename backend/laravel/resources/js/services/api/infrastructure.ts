/**
 * Infrastructure (devices instances + channel bindings + unassigned errors).
 *
 * Эндпоинты:
 *   POST /api/infrastructure-instances
 *   POST /api/channel-bindings
 *   GET  /api/unassigned-node-errors
 */
import { apiGet, apiPost, apiDelete } from './_client'

export type InfrastructureInstancePayload = Record<string, unknown>
export type ChannelBindingPayload = Record<string, unknown>

export interface UnassignedErrorItem {
  id: number
  node_uid?: string
  message?: string
  [key: string]: unknown
}

export interface UnassignedErrorsResponse {
  data: UnassignedErrorItem[]
  meta?: Record<string, unknown>
}

export const infrastructureApi = {
  createInstance(payload: InfrastructureInstancePayload): Promise<unknown> {
    return apiPost<unknown>('/infrastructure-instances', payload)
  },

  createChannelBinding(payload: ChannelBindingPayload): Promise<unknown> {
    return apiPost<unknown>('/channel-bindings', payload)
  },

  deleteChannelBinding(bindingId: number): Promise<unknown> {
    return apiDelete<unknown>(`/channel-bindings/${bindingId}`)
  },

  listZoneInstances(zoneId: number): Promise<unknown> {
    return apiGet<unknown>(`/zones/${zoneId}/infrastructure-instances`)
  },

  unassignedNodeErrors(params?: Record<string, unknown>): Promise<UnassignedErrorsResponse> {
    return apiGet<UnassignedErrorsResponse>('/unassigned-node-errors', { params })
  },
}
