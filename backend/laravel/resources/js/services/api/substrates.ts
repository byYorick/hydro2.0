/**
 * Substrates API client.
 */
import { apiGet, apiPost, apiPatch, apiDelete } from './_client'

export interface SubstrateComponent {
  name: string
  label?: string | null
  ratio_pct: number
}

export interface Substrate {
  id: number
  code: string
  name: string
  components: SubstrateComponent[]
  applicable_systems: string[]
  notes?: string | null
  created_at?: string
  updated_at?: string
}

export type SubstratePayload = Omit<Substrate, 'id' | 'created_at' | 'updated_at'> & { id?: number }

export const substratesApi = {
  list(): Promise<Substrate[]> {
    return apiGet<Substrate[]>('/substrates')
  },

  create(payload: SubstratePayload): Promise<Substrate> {
    return apiPost<Substrate>('/substrates', payload)
  },

  update(id: number, payload: SubstratePayload): Promise<Substrate> {
    return apiPatch<Substrate>(`/substrates/${id}`, payload)
  },

  delete(id: number): Promise<void> {
    return apiDelete<void>(`/substrates/${id}`)
  },
}
