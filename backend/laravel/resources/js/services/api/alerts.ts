/**
 * Alerts domain API client.
 *
 * Эндпоинты:
 *   GET   /api/alerts                       — список с фильтрами
 *   GET   /api/alerts/catalog               — справочник кодов алертов
 *   PATCH /api/alerts/:id/ack               — подтвердить (resolve) алерт
 */
import type { Alert } from '@/types/Alert'
import type { AlertSeverity } from '@/constants/alertErrorMap'
import { apiGet, apiPatch } from './_client'

export interface AlertListParams {
  status?: string
  zone_id?: number
  source?: string
  severity?: string
  category?: string
  [key: string]: string | number | undefined
}

/**
 * Backend `/api/alerts` возвращает `{ data: { data: [...] } }` или
 * `{ data: [...] }` в зависимости от версии. `apiGet` снимает внешний слой,
 * а здесь мы нормализуем оставшуюся вариативность.
 */
export interface AlertsListResponse {
  data?: Alert[]
  [key: string]: unknown
}

export interface AlertCatalogItem {
  code: string
  title: string
  description: string
  recommendation?: string
  severity?: AlertSeverity
}

export interface AlertCatalogResponse {
  items?: AlertCatalogItem[]
  [key: string]: unknown
}

export const alertsApi = {
  async list(params?: AlertListParams): Promise<Alert[]> {
    const response = await apiGet<AlertsListResponse | Alert[]>('/alerts', { params })
    if (Array.isArray(response)) {
      return response
    }
    return Array.isArray(response?.data) ? response.data : []
  },

  catalog(): Promise<AlertCatalogResponse> {
    return apiGet<AlertCatalogResponse>('/alerts/catalog')
  },

  acknowledge(alertId: number): Promise<Alert> {
    return apiPatch<Alert>(`/alerts/${alertId}/ack`, {})
  },
}
