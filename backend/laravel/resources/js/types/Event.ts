import type { Zone } from './Zone'

/**
 * Тип события
 */
export type EventKind = 'ALERT' | 'WARNING' | 'INFO' | 'SUCCESS'

/**
 * Модель события
 */
export interface Event {
  id: number
  kind: EventKind
  zone_id?: number
  zone?: Zone
  message: string
  occurred_at: string
  created_at?: string
}

