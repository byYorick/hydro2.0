/**
 * Telemetry aggregates API client.
 *
 * Эндпоинты:
 *   GET /api/telemetry/aggregates
 */
import { apiGet } from './_client'

export interface TelemetryAggregateParams {
  zone_id: number
  metric: string
  period: string
  [key: string]: unknown
}

export const telemetryApi = {
  aggregates<T = unknown>(params: TelemetryAggregateParams): Promise<T> {
    return apiGet<T>('/telemetry/aggregates', { params })
  },
}
