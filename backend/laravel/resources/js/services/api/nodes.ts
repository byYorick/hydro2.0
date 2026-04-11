/**
 * Nodes (ESP32 devices) API client.
 *
 * Эндпоинты:
 *   GET   /api/nodes                          — список с фильтрами
 *   PATCH /api/nodes/:id                      — обновить ноду (в т.ч. zone_id)
 *   POST  /api/nodes/:id/detach               — отвязать ноду от зоны
 *   POST  /api/nodes/:id/lifecycle/transition — сменить lifecycle-состояние
 */
import type { Device } from '@/types'
import { apiGet, apiPatch, apiPost, apiDelete } from './_client'

export interface NodesListParams {
  unassigned?: boolean
  zone_id?: number
  greenhouse_id?: number
  include_unassigned?: boolean
  search?: string
  [key: string]: string | number | boolean | undefined
}

export interface NodeUpdatePayload {
  zone_id?: number | null
  [key: string]: unknown
}

export interface NodeLifecycleTransitionPayload {
  target_state: string
  reason?: string
  [key: string]: unknown
}

export const nodesApi = {
  list(params?: NodesListParams): Promise<Device[]> {
    return apiGet<Device[]>('/nodes', { params })
  },

  update(nodeId: number, payload: NodeUpdatePayload): Promise<Device> {
    return apiPatch<Device>(`/nodes/${nodeId}`, payload)
  },

  detach(nodeId: number): Promise<Device> {
    return apiPost<Device>(`/nodes/${nodeId}/detach`, {})
  },

  lifecycleTransition<T = unknown>(
    nodeId: number,
    payload: NodeLifecycleTransitionPayload,
  ): Promise<T> {
    return apiPost<T>(`/nodes/${nodeId}/lifecycle/transition`, payload)
  },

  getLifecycleAllowedTransitions<T = unknown>(nodeId: number): Promise<T> {
    return apiGet<T>(`/nodes/${nodeId}/lifecycle/allowed-transitions`)
  },

  /**
   * Получить конфиг ноды.
   */
  getConfig(nodeId: number): Promise<Record<string, unknown>> {
    return apiGet<Record<string, unknown>>(`/nodes/${nodeId}/config`)
  },

  /**
   * Опубликовать (применить) конфиг ноды.
   */
  publishConfig(nodeId: number, payload: Record<string, unknown>): Promise<unknown> {
    return apiPost<unknown>(`/nodes/${nodeId}/config/publish`, payload)
  },

  /**
   * История телеметрии по ноде с фильтрами (metric/channel/from/to).
   */
  getTelemetryHistory(
    nodeId: number,
    params: Record<string, unknown>,
  ): Promise<Array<{ ts: string; value: number; channel?: string }>> {
    return apiGet<Array<{ ts: string; value: number; channel?: string }>>(
      `/nodes/${nodeId}/telemetry/history`,
      { params },
    )
  },

  /**
   * Удалить ноду (DELETE /nodes/:id).
   */
  delete(nodeId: number): Promise<void> {
    return apiDelete<void>(`/nodes/${nodeId}`)
  },
}
