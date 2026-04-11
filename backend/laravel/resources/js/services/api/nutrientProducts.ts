/**
 * Nutrient products API client.
 */
import type { NutrientProduct } from '@/types'
import { apiGet, apiPost, apiPatch, apiDelete } from './_client'

export type NutrientProductPayload = Omit<NutrientProduct, 'id'> & { id?: number }

export const nutrientProductsApi = {
  list(): Promise<NutrientProduct[]> {
    return apiGet<NutrientProduct[]>('/nutrient-products')
  },

  create(payload: NutrientProductPayload): Promise<NutrientProduct> {
    return apiPost<NutrientProduct>('/nutrient-products', payload)
  },

  update(id: number, payload: NutrientProductPayload): Promise<NutrientProduct> {
    return apiPatch<NutrientProduct>(`/nutrient-products/${id}`, payload)
  },

  delete(id: number): Promise<void> {
    return apiDelete<void>(`/nutrient-products/${id}`)
  },
}
