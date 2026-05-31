/**
 * Greenhouses domain API client.
 *
 * Эндпоинты:
 *   GET  /api/greenhouses
 *   POST /api/greenhouses
 *   GET  /api/greenhouse-types                                  — справочник типов
 *   GET  /api/greenhouses/{id}/climate/state                    — climate state read
 *   POST /api/greenhouses/{id}/climate/control-mode             — переключить режим
 *   POST /api/greenhouses/{id}/climate/manual-override          — ручной override
 *   DELETE /api/greenhouses/{id}/climate/manual-override        — сбросить override
 */
import type { Greenhouse } from '@/types'
import { normalizePaginatedList } from '@/utils/apiHelpers'
import { apiDelete, apiGet, apiPost } from './_client'

export interface GreenhouseType {
  id: number
  code: string
  name: string
  [key: string]: unknown
}

export interface GreenhouseCreatePayload {
  uid: string
  name: string
  type?: string | null
  greenhouse_type_id?: number | null
  timezone?: string | null
  description?: string | null
  [key: string]: unknown
}

export type ClimateControlMode = 'auto' | 'semi' | 'manual'

export interface ClimateStateEnvelope {
  data?: { state?: unknown } | unknown
}

export interface ClimateControlModePayload {
  control_mode: ClimateControlMode
}

export interface ClimateManualOverridePayload {
  left_position_pct: number
  right_position_pct: number
  ttl_sec: number
  return_mode: string
  reason?: string | null
}

export const greenhousesApi = {
  async list(): Promise<Greenhouse[]> {
    const response = await apiGet<unknown>('/greenhouses')
    return normalizePaginatedList<Greenhouse>(response)
  },

  create(payload: GreenhouseCreatePayload): Promise<Greenhouse> {
    return apiPost<Greenhouse>('/greenhouses', payload)
  },

  types(): Promise<GreenhouseType[]> {
    return apiGet<GreenhouseType[]>('/greenhouse-types')
  },

  getById(greenhouseId: number): Promise<Greenhouse> {
    return apiGet<Greenhouse>(`/greenhouses/${greenhouseId}`)
  },

  /**
   * S2.5 (AUDIT_2026_05_28_BUGFIX_PLAN): climate endpoints вынесены из
   * `Pages/Greenhouses/Climate.vue`, где они напрямую вызывались через
   * `axios.*` (нарушение границы services/api).
   */
  climate: {
    /** Возвращает текущий снимок climate state греенхауза. */
    state(greenhouseId: number): Promise<unknown> {
      return apiGet<unknown>(`/greenhouses/${greenhouseId}/climate/state`)
    },

    /** Переключение control-mode (auto/semi/manual). */
    setControlMode(
      greenhouseId: number,
      payload: ClimateControlModePayload,
    ): Promise<unknown> {
      return apiPost<unknown>(
        `/greenhouses/${greenhouseId}/climate/control-mode`,
        payload,
      )
    },

    /** Применить ручной override позиций. */
    setManualOverride(
      greenhouseId: number,
      payload: ClimateManualOverridePayload,
    ): Promise<void> {
      return apiPost<void>(
        `/greenhouses/${greenhouseId}/climate/manual-override`,
        payload,
      )
    },

    /** Сбросить ручной override. */
    clearManualOverride(greenhouseId: number): Promise<void> {
      return apiDelete<void>(`/greenhouses/${greenhouseId}/climate/manual-override`)
    },
  },
}
