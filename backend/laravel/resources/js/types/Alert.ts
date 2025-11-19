import type { Zone } from './Zone'

/**
 * Тип алерта
 */
export type AlertType = string

/**
 * Статус алерта
 */
export type AlertStatus = 'active' | 'resolved' | 'RESOLVED' | 'ACTIVE'

/**
 * Модель алерта
 */
export interface Alert {
  id: number
  type: AlertType
  zone_id?: number
  zone?: Zone
  status: AlertStatus
  message?: string
  created_at: string
  updated_at?: string
  resolved_at?: string
}
