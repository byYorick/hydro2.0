/**
 * Composable для централизованной работы с API
 * Использует единый apiClient из utils/apiClient.ts
 */
import apiClient, { setToastHandler, type ToastHandler, type AxiosRequestConfig } from '@/utils/apiClient'
import { useToast } from '@/composables/useToast'
import type { AxiosInstance } from 'axios'

// Реэкспортируем тип для обратной совместимости
export type { ToastHandler }

/**
 * Composable для работы с API
 * @param showToast - Опциональная функция для показа Toast уведомлений (если не установлен глобальный)
 * @returns Объект с методами для работы с API
 */
export function useApi(showToast: ToastHandler | null = null) {
  const { showToast: fallbackShowToast } = useToast()

  // Всегда устанавливаем обработчик toast:
  // 1) Явно переданный showToast имеет приоритет
  // 2) Иначе используем глобальный из useToast
  setToastHandler((showToast && typeof showToast === 'function') ? showToast : fallbackShowToast)

  return {
    api: apiClient as AxiosInstance,
    get: <T = unknown>(url: string, config?: AxiosRequestConfig) => apiClient.get<T>(url, config),
    post: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => apiClient.post<T>(url, data, config),
    patch: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => apiClient.patch<T>(url, data, config),
    put: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => apiClient.put<T>(url, data, config),
    delete: <T = unknown>(url: string, config?: AxiosRequestConfig) => apiClient.delete<T>(url, config),
  }
}
