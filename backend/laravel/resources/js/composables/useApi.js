/**
 * Composable для централизованной работы с API
 */
import axios from 'axios'

// Создаем настроенный экземпляр axios
const api = axios.create({
  headers: {
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Глобальная функция для показа Toast (будет установлена через setToastHandler)
let globalShowToast = null

/**
 * Устанавливает глобальный обработчик Toast уведомлений
 * @param {Function} showToast - Функция для показа Toast уведомлений
 */
export function setToastHandler(showToast) {
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
 * @param {Function} showToast - Опциональная функция для показа Toast уведомлений (если не установлен глобальный)
 * @returns {Object} Объект с методами для работы с API
 */
export function useApi(showToast = null) {
  // Если передана функция showToast, устанавливаем её как глобальную
  if (showToast && typeof showToast === 'function') {
    setToastHandler(showToast)
  }

  return {
    api,
    get: (url, config = {}) => api.get(url, config),
    post: (url, data = {}, config = {}) => api.post(url, data, config),
    patch: (url, data = {}, config = {}) => api.patch(url, data, config),
    put: (url, data = {}, config = {}) => api.put(url, data, config),
    delete: (url, config = {}) => api.delete(url, config),
  }
}

