/**
 * Service logs API client.
 *
 * Эндпоинт: GET /api/logs/service с фильтрами.
 */
import { apiGet } from './_client'

export interface LogsListParams {
  service?: string
  level?: string
  search?: string
  from?: string
  to?: string
  page?: number
  per_page?: number
  [key: string]: string | number | undefined
}

/**
 * Backend отвечает в нескольких форматах: `{status, data, meta}` или
 * `{data:{data,meta}}` или чистый массив. Возвращаем сырой payload,
 * а нормализация остаётся в Page-компоненте.
 */
export const logsApi = {
  list(params: LogsListParams = {}): Promise<unknown> {
    return apiGet<unknown>('/logs/service', { params })
  },
}
