/**
 * Reconciliation Contract - формальное описание формата snapshot
 * 
 * Определяет типы для reconciliation данных, получаемых от backend
 * при переподключении WebSocket соединения
 */

/**
 * Телеметрия зоны (последние значения метрик)
 */
export interface ZoneTelemetry {
  zone_id: number
  timestamp: string
  temperature?: number
  humidity?: number
  ph?: number
  ec?: number
  water_level?: number
  [key: string]: unknown // Допускаем дополнительные метрики
}

/**
 * Команда устройства
 */
export interface ZoneCommand {
  id: string | number
  command_id?: string | number
  zone_id: number
  node_id?: number
  device_id?: number
  command_type: string
  status: 'QUEUED' | 'SENT' | 'ACK' | 'DONE' | 'NO_EFFECT' | 'ERROR' | 'INVALID' | 'BUSY' | 'TIMEOUT' | 'SEND_FAILED'
  message?: string
  error?: string
  created_at: string
  updated_at: string
  server_ts?: number // Timestamp сервера для reconciliation
}

/**
 * Алерт зоны
 */
export interface ZoneAlert {
  id: number | string
  zone_id: number
  type: string
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  status: 'ACTIVE' | 'RESOLVED' | 'ACKNOWLEDGED'
  message: string
  occurred_at: string
  resolved_at?: string
  acknowledged_at?: string
  metadata?: Record<string, unknown>
}

/**
 * Узел устройства в зоне
 */
export interface ZoneNode {
  id: number | string
  node_id?: number | string
  zone_id: number
  device_id?: number
  name: string
  type: string
  status: 'ONLINE' | 'OFFLINE' | 'ERROR'
  last_seen?: string
  metadata?: Record<string, unknown>
}

/**
 * Snapshot зоны - полное состояние зоны на момент переподключения
 * 
 * Используется для reconciliation: сравнения локального состояния
 * с состоянием на сервере и синхронизации данных
 */
export interface ZoneSnapshot {
  /**
   * Уникальный ID snapshot (UUID или timestamp-based)
   */
  snapshot_id: string
  
  /**
   * Timestamp сервера в миллисекундах (для сравнения с событиями)
   * События с server_ts < snapshot.server_ts игнорируются как устаревшие
   */
  server_ts: number
  
  /**
   * ID зоны
   */
  zone_id: number
  
  /**
   * Последние значения телеметрии
   */
  telemetry: Record<string, ZoneTelemetry>
  
  /**
   * Активные алерты зоны
   */
  active_alerts: ZoneAlert[]
  
  /**
   * Недавние команды (для отслеживания статусов)
   */
  recent_commands: ZoneCommand[]
  
  /**
   * Узлы устройств в зоне
   */
  nodes: ZoneNode[]
  
  /**
   * Дополнительные метаданные (опционально)
   */
  metadata?: Record<string, unknown>
}

/**
 * Reconciliation данные - полный набор данных для синхронизации
 * 
 * Отправляется от backend при переподключении WebSocket
 * через событие 'ws:reconciliation'
 */
export interface ReconciliationData {
  /**
   * Телеметрия для всех активных зон
   */
  telemetry?: ZoneTelemetry[]
  
  /**
   * Команды для всех активных зон
   */
  commands?: ZoneCommand[]
  
  /**
   * Алерты для всех активных зон
   */
  alerts?: ZoneAlert[]
  
  /**
   * Timestamp сервера (для логирования и отладки)
   */
  timestamp?: string
  
  /**
   * Дополнительные метаданные
   */
  metadata?: Record<string, unknown>
}

/**
 * Backend контракт для reconciliation endpoint
 * 
 * GET /api/zones/{zoneId}/snapshot
 * 
 * Response:
 * {
 *   "status": "ok",
 *   "data": ZoneSnapshot
 * }
 */
export interface SnapshotResponse {
  status: 'ok' | 'error'
  data?: ZoneSnapshot
  error?: string
  message?: string
}

export type SnapshotHandler = (snapshot: ZoneSnapshot) => void

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Проверка валидности snapshot
 */
export function isValidSnapshot(snapshot: unknown): snapshot is ZoneSnapshot {
  if (!isRecord(snapshot)) {
    return false
  }

  return (
    typeof snapshot.snapshot_id === 'string' &&
    typeof snapshot.server_ts === 'number' &&
    typeof snapshot.zone_id === 'number' &&
    isRecord(snapshot.telemetry) &&
    Array.isArray(snapshot.active_alerts) &&
    Array.isArray(snapshot.recent_commands) &&
    Array.isArray(snapshot.nodes)
  )
}

/**
 * Проверка валидности reconciliation данных
 */
export function isValidReconciliationData(data: unknown): data is ReconciliationData {
  if (!isRecord(data)) {
    return false
  }

  return (
    (
      data.telemetry === undefined || Array.isArray(data.telemetry)
    ) &&
    (
      data.commands === undefined || Array.isArray(data.commands)
    ) &&
    (
      data.alerts === undefined || Array.isArray(data.alerts)
    )
  )
}
