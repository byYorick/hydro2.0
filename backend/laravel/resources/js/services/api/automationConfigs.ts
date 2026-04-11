/**
 * Automation configs API client.
 *
 * Generic key-value authority-store над /api/automation-configs/:scope/:id/:namespace
 * Используется correction, pid, calibration, pump settings, logic profiles.
 */
import { apiGet, apiPut, apiPost, apiDelete } from './_client'

export type AutomationConfigScope = 'system' | 'greenhouse' | 'zone' | 'grow_cycle'

export interface AutomationConfigDocument {
  payload: Record<string, unknown>
  [key: string]: unknown
}

export const automationConfigsApi = {
  get<T = AutomationConfigDocument>(
    scope: AutomationConfigScope,
    id: number,
    namespace: string,
  ): Promise<T> {
    return apiGet<T>(`/automation-configs/${scope}/${id}/${namespace}`)
  },

  update<T = AutomationConfigDocument>(
    scope: AutomationConfigScope,
    id: number,
    namespace: string,
    payload: Record<string, unknown>,
  ): Promise<T> {
    return apiPut<T>(
      `/automation-configs/${scope}/${id}/${namespace}`,
      { payload },
    )
  },

  validate(
    scope: AutomationConfigScope,
    id: number,
    namespace: string,
    payload: Record<string, unknown>,
  ): Promise<unknown> {
    return apiPost<unknown>(
      `/automation-configs/${scope}/${id}/${namespace}/validate`,
      payload,
    )
  },

  reset<T = AutomationConfigDocument>(
    scope: AutomationConfigScope,
    id: number,
    namespace: string,
  ): Promise<T> {
    return apiDelete<T>(`/automation-configs/${scope}/${id}/${namespace}`)
  },

  getHistory<T = unknown>(
    scope: AutomationConfigScope,
    id: number,
    namespace: string,
  ): Promise<T[]> {
    return apiGet<T[]>(`/automation-configs/${scope}/${id}/${namespace}/history`)
  },
}
