/**
 * Greenhouses domain API client.
 *
 * Эндпоинты:
 *   GET  /api/greenhouses
 *   POST /api/greenhouses
 *   GET  /api/greenhouse-types      — справочник типов (read-only lookup)
 */
import type { Greenhouse } from '@/types'
import { apiGet, apiPost } from './_client'

export interface GreenhouseType {
  id: number
  code: string
  name: string
  [key: string]: unknown
}

export interface GreenhouseCreatePayload {
  name: string
  type?: string | null
  [key: string]: unknown
}

export const greenhousesApi = {
  list(): Promise<Greenhouse[]> {
    return apiGet<Greenhouse[]>('/greenhouses')
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
}
