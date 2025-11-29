/**
 * Composable для централизованной работы с API
 */
import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { logger } from '@/utils/logger'
import { ERROR_MESSAGES } from '@/constants/messages'

// Тип функции для показа Toast
export type ToastHandler = (message: string, variant?: string, duration?: number) => void

// Создаем настроенный экземпляр axios
const api: AxiosInstance = axios.create({
  headers: {
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Request interceptor для добавления префикса /api к запросам, которые его не имеют
api.interceptors.request.use(
  (config) => {
    // Если URL не начинается с /api/ или /settings/, и не является абсолютным URL, добавляем /api
    if (config.url && !config.url.startsWith('/api/') && !config.url.startsWith('/settings/') && !config.url.startsWith('http')) {
      config.url = `/api${config.url}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

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
    // Игнорируем отмененные запросы (Inertia.js)
    // Это нормальное поведение при навигации - не логируем как ошибку
    if (error?.code === 'ERR_CANCELED' || 
        error?.name === 'CanceledError' || 
        error?.message === 'canceled' ||
        error?.message === 'Request aborted') {
      // Не логируем отмененные запросы - это нормальное поведение Inertia.js
      return Promise.reject(error)
    }

    const message = error.response?.data?.message || error.message || ERROR_MESSAGES.UNKNOWN
    const status = error.response?.status
    
    // Логируем ошибку (но не логируем 401 постоянно, чтобы не засорять консоль)
    if (status !== 401) {
      logger.error('[API Error]', {
        url: error.config?.url,
        method: error.config?.method,
        status,
        message,
      })
    }
    
    // 401 - не показываем Toast и не логируем постоянно, обычно это обрабатывается на уровне auth
    // Множественные 401 могут происходить из-за интервалов обновления
    if (globalShowToast && status !== 401) {
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

