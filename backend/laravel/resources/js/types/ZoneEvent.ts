import type { Zone } from './Zone'

/**
 * Тип события
 */
export type EventKind = 'ALERT' | 'WARNING' | 'INFO' | 'SUCCESS'

/**
 * Модель события
 */
export interface ZoneEvent {
  id: number
  kind: EventKind
  zone_id?: number
  zone?: Zone
  message: string
  occurred_at: string
  created_at?: string
}

// Экспортируем для обратной совместимости (но не используем в новых файлах из-за конфликта с встроенным Event)
// export type Event = ZoneEvent

