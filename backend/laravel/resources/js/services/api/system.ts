/**
 * System health / status API client.
 *
 * Эндпоинты:
 *   GET /api/system/health — агрегированный статус сервисов (app/db/mqtt/...)
 */
import { apiGet } from './_client'

export interface SystemHealthPayload {
  app?: string
  db?: string
  mqtt?: string
  history_logger?: string
  automation_engine?: string
  [key: string]: unknown
}

export interface SchedulerDispatchSnapshot {
  scope: 'global'
  generated_at: string
  enabled: boolean
  dispatch_token_configured?: boolean
  dispatch_interval_sec: number
  last_cycle_at: string | null
  last_cycle_age_sec: number | null
  cycle_observation: 'disabled' | 'not_observed' | 'recent' | 'delayed'
  pending_intents: number | null
  oldest_pending_age_sec: number | null
  cycle_duration_p99_sec: number | null
  cycle_overrun_sec: number | null
}

export const systemApi = {
  schedulerObservability(): Promise<SchedulerDispatchSnapshot> {
    return apiGet<SchedulerDispatchSnapshot>('/system/scheduler/observability', { skipErrorToast: true })
  },
  health(): Promise<SystemHealthPayload> {
    return apiGet<SystemHealthPayload>('/system/health')
  },
}
