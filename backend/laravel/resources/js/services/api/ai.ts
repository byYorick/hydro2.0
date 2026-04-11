/**
 * AI prediction API client.
 *
 * Эндпоинт:
 *   POST /api/ai/predict  — запрашивает прогноз метрики для зоны
 */
import { apiClient } from './_client'

export interface PredictionRequest {
  zone_id: number
  metric_type: string
  horizon_minutes: number
}

/**
 * PredictionResponse содержит метаданные статуса, поэтому возвращаем сырой
 * payload (status + data или message/reason при недостатке данных).
 */
export interface PredictionResponse {
  status: 'ok' | 'insufficient' | 'error' | string
  data?: {
    predicted_value: number | null
    confidence?: number
    [key: string]: unknown
  }
  message?: string
  reason?: string
  [key: string]: unknown
}

export const aiApi = {
  /**
   * POST /api/ai/predict
   *
   * Возвращает raw payload, т.к. статус и detail handling остаётся на
   * usage-site (компоненты AIPredictionCard / ZoneAIPredictionHint
   * обрабатывают 'insufficient' / 'error' состояния отдельно).
   */
  async predict(request: PredictionRequest): Promise<PredictionResponse> {
    const response = await apiClient.post<PredictionResponse>('/ai/predict', request)
    return response.data
  },
}
