/**
 * Модель теплицы
 */
export interface Greenhouse {
  id: number
  name: string
  description?: string
  location?: string
  type?: string
  uid?: string
  zones_count?: number
  zones_running?: number
  created_at?: string
  updated_at?: string
}

