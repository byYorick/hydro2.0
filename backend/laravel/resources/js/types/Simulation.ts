import type { SimulationReportPhase } from '@/composables/useSimulationPresentation'

/**
 * Действие, зарегистрированное в ходе симуляции (команда или событие)
 */
export interface SimulationAction {
  kind: 'command' | 'event'
  id: number
  summary?: string | null
  cmd?: string | null
  event_type?: string | null
  created_at?: string | null
}

/**
 * Текущий статус PID-контроллера в рамках симуляции
 */
export interface SimulationPidStatus {
  type: string
  current?: number | null
  target?: number | null
  output?: number | null
  zone_state?: string | null
  error?: string | null
  updated_at?: string | null
}

/**
 * Отчёт по завершённой симуляции
 */
export interface SimulationReport {
  id: number
  simulation_id: number
  zone_id: number
  status: string
  started_at?: string | null
  finished_at?: string | null
  summary_json?: Record<string, unknown> | null
  phases_json?: SimulationReportPhase[] | null
  metrics_json?: Record<string, unknown> | null
  errors_json?: unknown
}
