/**
 * Composable для работы с rate-limited API запросами с exponential backoff.
 *
 * Единственный composable, которому разрешено импортировать `apiClient`
 * напрямую — он нуждается в raw-axios для чтения заголовка `Retry-After`
 * и для повторного выполнения неизменного запроса при 429. Все остальные
 * consumer'ы должны ходить через `import { api } from '@/services/api'`.
 */
import { ref, type Ref } from 'vue'
import type { AxiosRequestConfig, AxiosResponse } from 'axios'
// eslint-disable-next-line no-restricted-imports
import { apiClient } from '@/services/api/_client'
import type { ToastHandler } from '@/services/api'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface AxiosLikeError {
  message?: string
  response?: {
    status?: number
    headers?: Record<string, string>
  }
}

export interface RateLimitedRequestOptions {
  retries?: number
  backoff?: 'exponential' | 'linear'
  baseDelay?: number // базовая задержка в миллисекундах
  maxDelay?: number // максимальная задержка в миллисекундах
}

export function useRateLimitedApi(showToast?: ToastHandler) {
  const isProcessing: Ref<boolean> = ref(false)

  /**
   * Sleep утилита
   */
  function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * Вычислить задержку для retry
   */
  function calculateDelay(
    attempt: number,
    options: RateLimitedRequestOptions
  ): number {
    const {
      backoff = 'exponential',
      baseDelay = 1000,
      maxDelay = 30000,
    } = options

    let delay: number

    if (backoff === 'exponential') {
      // Exponential backoff: baseDelay * 2^attempt
      delay = baseDelay * Math.pow(2, attempt)
    } else {
      // Linear backoff: baseDelay * (attempt + 1)
      delay = baseDelay * (attempt + 1)
    }

    // Ограничиваем максимальной задержкой
    return Math.min(delay, maxDelay)
  }

  /**
   * Выполнить запрос с учетом rate limiting и retry логики
   */
  async function rateLimitedRequest<T>(
    requestFn: () => Promise<AxiosResponse<T>>,
    options: RateLimitedRequestOptions = {}
  ): Promise<AxiosResponse<T>> {
    const {
      retries = 3,
      backoff = 'exponential',
      baseDelay = 1000,
      maxDelay = 30000,
    } = options

    let lastError: unknown = null

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const result = await requestFn()

        // Успешный запрос - сбрасываем счетчик ошибок
        if (attempt > 0) {
          logger.info(`[useRateLimitedApi] Request succeeded after ${attempt} retries`)
        }

        return result
      } catch (err) {
        lastError = err
        const error = err as AxiosLikeError

        // Проверяем, является ли ошибка rate limit (429)
        const isRateLimit = error.response?.status === 429

        // Проверяем, есть ли заголовок Retry-After
        const retryAfter = error.response?.headers?.['retry-after']
        
        if (isRateLimit && retryAfter) {
          // Используем значение из Retry-After заголовка
          const delayMs = parseInt(retryAfter, 10) * 1000
          
          logger.warn(`[useRateLimitedApi] Rate limit hit, retrying after ${delayMs}ms (from Retry-After header)`)
          
          if (showToast && attempt === 0) {
            showToast('Превышен лимит запросов. Повторная попытка...', 'warning', TOAST_TIMEOUT.NORMAL)
          }
          
          await sleep(delayMs)
          continue
        }
        
        // Если это последняя попытка, выбрасываем ошибку
        if (attempt === retries) {
          if (isRateLimit) {
            logger.error(`[useRateLimitedApi] Rate limit exceeded after ${retries} retries`)
            if (showToast) {
              showToast('Превышен лимит запросов. Попробуйте позже.', 'error', TOAST_TIMEOUT.LONG)
            }
          }
          throw err
        }
        
        // Вычисляем задержку для retry
        const delay = retryAfter 
          ? parseInt(retryAfter, 10) * 1000 
          : calculateDelay(attempt, { backoff, baseDelay, maxDelay })
        
        if (isRateLimit) {
          logger.warn(`[useRateLimitedApi] Rate limit hit, retrying after ${delay}ms (attempt ${attempt + 1}/${retries})`)
        } else {
          logger.warn(`[useRateLimitedApi] Request failed, retrying after ${delay}ms (attempt ${attempt + 1}/${retries}):`, error.message)
        }
        
        if (showToast && attempt === 0 && !isRateLimit) {
          showToast('Ошибка запроса. Повторная попытка...', 'warning', TOAST_TIMEOUT.NORMAL)
        }
        
        await sleep(delay)
      }
    }
    
    // Не должно достигнуть сюда, но на всякий случай
    throw lastError || new Error('Request failed after all retries')
  }

  /**
   * Обертка для GET запросов с rate limiting
   */
  async function rateLimitedGet<T = unknown>(
    url: string,
    config?: AxiosRequestConfig,
    options?: RateLimitedRequestOptions
  ): Promise<AxiosResponse<T>> {
    return rateLimitedRequest(
      () => apiClient.get<T>(url, config),
      options
    )
  }

  /**
   * Обертка для POST запросов с rate limiting
   */
  async function rateLimitedPost<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig,
    options?: RateLimitedRequestOptions
  ): Promise<AxiosResponse<T>> {
    return rateLimitedRequest(
      () => apiClient.post<T>(url, data, config),
      options
    )
  }

  /**
   * Обертка для PATCH запросов с rate limiting
   */
  async function rateLimitedPatch<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig,
    options?: RateLimitedRequestOptions
  ): Promise<AxiosResponse<T>> {
    return rateLimitedRequest(
      () => apiClient.patch<T>(url, data, config),
      options
    )
  }

  /**
   * Обертка для DELETE запросов с rate limiting
   */
  async function rateLimitedDelete<T = unknown>(
    url: string,
    config?: AxiosRequestConfig,
    options?: RateLimitedRequestOptions
  ): Promise<AxiosResponse<T>> {
    return rateLimitedRequest(
      () => apiClient.delete<T>(url, config),
      options
    )
  }

  return {
    isProcessing,
    rateLimitedRequest,
    rateLimitedGet,
    rateLimitedPost,
    rateLimitedPatch,
    rateLimitedDelete,
  }
}
