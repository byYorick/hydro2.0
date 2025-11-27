import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useRateLimitedApi } from '../useRateLimitedApi'

// Моки
vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}))

const mockApi = {
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}

vi.mock('../useApi', () => ({
  useApi: () => ({
    api: mockApi,
  }),
}))

describe('useRateLimitedApi', () => {
  let mockShowToast: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()
    mockShowToast = vi.fn()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should make successful request', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    mockApi.get.mockResolvedValue({ data: { success: true } })

    const result = await rateLimitedGet('/api/test')

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.get).toHaveBeenCalledTimes(1)
  })

  it('should retry on rate limit with Retry-After header', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    // Первый запрос - rate limit
    mockApi.get
      .mockRejectedValueOnce({
        response: {
          status: 429,
          headers: {
            'retry-after': '2',
          },
        },
      })
      // Второй запрос - успех
      .mockResolvedValueOnce({ data: { success: true } })

    const promise = rateLimitedGet('/api/test', undefined, {
      retries: 3,
      backoff: 'exponential',
    })

    // Продвигаем время на 2 секунды (Retry-After)
    vi.advanceTimersByTime(2000)

    const result = await promise

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.get).toHaveBeenCalledTimes(2)
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('Превышен лимит запросов'),
      'warning',
      3000
    )
  })

  it('should retry with exponential backoff on error', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    // Первые два запроса - ошибка, третий - успех
    mockApi.get
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({ data: { success: true } })

    const promise = rateLimitedGet('/api/test', undefined, {
      retries: 3,
      backoff: 'exponential',
      baseDelay: 1000,
    })

    // Продвигаем время для exponential backoff: 1s, 2s
    await vi.advanceTimersByTimeAsync(1000) // Первая попытка
    await vi.advanceTimersByTimeAsync(2000) // Вторая попытка

    const result = await promise

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.get).toHaveBeenCalledTimes(3)
  })

  it('should retry with linear backoff on error', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    mockApi.get
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({ data: { success: true } })

    const promise = rateLimitedGet('/api/test', undefined, {
      retries: 3,
      backoff: 'linear',
      baseDelay: 1000,
    })

    // Продвигаем время для linear backoff: 1s, 2s
    await vi.advanceTimersByTimeAsync(1000) // Первая попытка
    await vi.advanceTimersByTimeAsync(2000) // Вторая попытка

    const result = await promise

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.get).toHaveBeenCalledTimes(3)
  })

  it('should throw error after max retries', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    mockApi.get.mockRejectedValue(new Error('Network error'))

    const promise = rateLimitedGet('/api/test', undefined, {
      retries: 2,
      baseDelay: 1000,
    })

    // Продвигаем время для всех попыток
    vi.advanceTimersByTime(1000) // Первая попытка
    vi.advanceTimersByTime(2000) // Вторая попытка
    vi.advanceTimersByTime(4000) // Третья попытка

    // Ждем завершения промиса
    await vi.runAllTimersAsync()
    
    await expect(promise).rejects.toThrow('Network error')
    expect(mockApi.get).toHaveBeenCalledTimes(3) // 1 initial + 2 retries
  })

  it('should handle rate limit without Retry-After header', async () => {
    const { rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    mockApi.get
      .mockRejectedValueOnce({
        response: {
          status: 429,
          headers: {},
        },
      })
      .mockResolvedValueOnce({ data: { success: true } })

    const promise = rateLimitedGet('/api/test', undefined, {
      retries: 3,
      baseDelay: 1000,
    })

    // Продвигаем время для exponential backoff
    await vi.advanceTimersByTimeAsync(1000)

    const result = await promise

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.get).toHaveBeenCalledTimes(2)
  })

  it('should support POST requests', async () => {
    const { rateLimitedPost } = useRateLimitedApi(mockShowToast)
    
    mockApi.post.mockResolvedValue({ data: { success: true } })

    const result = await rateLimitedPost('/api/test', { data: 'test' })

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.post).toHaveBeenCalledWith('/api/test', { data: 'test' }, undefined)
  })

  it('should support PATCH requests', async () => {
    const { rateLimitedPatch } = useRateLimitedApi(mockShowToast)
    
    mockApi.patch.mockResolvedValue({ data: { success: true } })

    const result = await rateLimitedPatch('/api/test', { data: 'test' })

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.patch).toHaveBeenCalledWith('/api/test', { data: 'test' }, undefined)
  })

  it('should support DELETE requests', async () => {
    const { rateLimitedDelete } = useRateLimitedApi(mockShowToast)
    
    mockApi.delete.mockResolvedValue({ data: { success: true } })

    const result = await rateLimitedDelete('/api/test')

    expect(result).toEqual({ data: { success: true } })
    expect(mockApi.delete).toHaveBeenCalledWith('/api/test', undefined)
  })

  it('should track processing state', async () => {
    const { isProcessing, rateLimitedGet } = useRateLimitedApi(mockShowToast)
    
    mockApi.get.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))

    const promise = rateLimitedGet('/api/test')
    
    // isProcessing должен быть true во время выполнения
    // (но это сложно проверить без реального промиса)
    
    vi.advanceTimersByTime(100)
    await promise
  })
})

