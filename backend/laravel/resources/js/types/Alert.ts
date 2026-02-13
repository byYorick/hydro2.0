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
  source?: string
  code?: string
  severity?: 'info' | 'warning' | 'error' | 'critical' | string
  category?: string
  node_uid?: string
  hardware_id?: string
  error_count?: number
  status: AlertStatus
  message?: string
  details?: Record<string, unknown> | null
  created_at: string
  updated_at?: string
  resolved_at?: string
}
