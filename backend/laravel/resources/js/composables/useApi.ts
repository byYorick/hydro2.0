/**
 * Composable для централизованной работы с API
 */
import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

// Тип функции для показа Toast
export type ToastHandler = (message: string, variant?: string, duration?: number) => void

// Создаем настроенный экземпляр axios
const api: AxiosInstance = axios.create({
  headers: {
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Глобальная функция для показа Toast (будет установлена через setToastHandler)
let globalShowToast: ToastHandler | null = null

/**
 * Устанавливает глобальный обработчик Toast уведомлений
 */
export function setToastHandler(showToast: ToastHandler): void {
  globalShowToast = showToast
}

// Interceptor для обработки ошибок (добавляется один раз)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.message || error.message || 'Неизвестная ошибка'
    
    if (globalShowToast && error.response?.status !== 401) {
      // 401 - не показываем Toast, обычно это обрабатывается на уровне auth
      globalShowToast(`Ошибка: ${message}`, 'error', 5000)
    }
    
    return Promise.reject(error)
  }
)

/**
 * Composable для работы с API
 * @param showToast - Опциональная функция для показа Toast уведомлений (если не установлен глобальный)
 * @returns Объект с методами для работы с API
 */
export function useApi(showToast: ToastHandler | null = null) {
  // Если передана функция showToast, устанавливаем её как глобальную
  if (showToast && typeof showToast === 'function') {
    setToastHandler(showToast)
  }

  return {
    api,
    get: <T = unknown>(url: string, config?: AxiosRequestConfig) => api.get<T>(url, config),
    post: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.post<T>(url, data, config),
    patch: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.patch<T>(url, data, config),
    put: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => api.put<T>(url, data, config),
    delete: <T = unknown>(url: string, config?: AxiosRequestConfig) => api.delete<T>(url, config),
  }
}

