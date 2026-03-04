import type { Zone } from './Zone'

/**
 * Тип события
 */
export type EventKind = 'ALERT' | 'WARNING' | 'INFO' | 'ACTION' | 'SUCCESS'

/**
 * Модель события
 */
export interface ZoneEvent {
  id: number
  kind: string
  zone_id?: number
  zone?: Zone
  message: string
  occurred_at: string
  created_at?: string
  payload?: Record<string, unknown>
}

// Экспортируем для обратной совместимости (но не используем в новых файлах из-за конфликта с встроенным Event)
// export type Event = ZoneEvent
