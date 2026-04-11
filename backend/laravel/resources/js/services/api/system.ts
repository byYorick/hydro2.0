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

export const systemApi = {
  health(): Promise<SystemHealthPayload> {
    return apiGet<SystemHealthPayload>('/system/health')
  },
}
