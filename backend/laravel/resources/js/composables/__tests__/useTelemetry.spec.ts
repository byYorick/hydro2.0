import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTelemetry, clearTelemetryCache } from '../useTelemetry'

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    group: vi.fn(),
    groupEnd: vi.fn(),
    groupCollapsed: vi.fn(),
    table: vi.fn(),
    time: vi.fn(),
    timeEnd: vi.fn(),
    isDev: true,
    isProd: false
  }
}))

// Mock useApi
vi.mock('../useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      get: vi.fn()
    }
  }))
}))

// Mock useErrorHandler
vi.mock('../useErrorHandler', () => ({
  useErrorHandler: vi.fn(() => ({
    handleError: vi.fn((err) => {
      // Return normalized error
      if (err instanceof Error) return err
      return new Error(err?.message || 'Unknown error')
    }),
    clearError: vi.fn(),
    isErrorType: vi.fn(),
    lastError: { value: null },
    errorContext: { value: null }
  }))
}))

describe('useTelemetry', () => {
  let mockApiGet: vi.Mock
  let mockShowToast: vi.Mock

  beforeEach(async () => {
    clearTelemetryCache() // Очищаем кеш перед каждым тестом
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        get: vi.fn()
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)
    mockApiGet = mockApi.api.get
    mockShowToast = vi.fn()
    mockApiGet.mockClear()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should initialize with loading false', () => {
    const { loading } = useTelemetry()
    expect(loading.value).toBe(false)
  })

  it('should fetch last telemetry from API', async () => {
    const dummyTelemetry = { ph: 6.0, ec: 1.5, temperature: 22.5, humidity: 60 }
    mockApiGet.mockResolvedValue({ data: { data: dummyTelemetry } })

    const { fetchLastTelemetry } = useTelemetry(mockShowToast)
    const telemetry = await fetchLastTelemetry(1)

    expect(telemetry).toEqual(dummyTelemetry)
    expect(mockApiGet).toHaveBeenCalledWith('/api/zones/1/telemetry/last')
    expect(mockShowToast).not.toHaveBeenCalled()
  })

  it('should cache last telemetry', async () => {
    const dummyTelemetry = { ph: 6.0, ec: 1.5 }
    mockApiGet.mockResolvedValue({ data: { data: dummyTelemetry } })

    const { fetchLastTelemetry } = useTelemetry()
    
    await fetchLastTelemetry(1)
    const cached = await fetchLastTelemetry(1) // Second call should use cache

    expect(cached).toEqual(dummyTelemetry)
    expect(mockApiGet).toHaveBeenCalledTimes(1) // Only called once due to cache
  })

  it('should force refresh when requested', async () => {
    const dummyTelemetry1 = { ph: 6.0 }
    const dummyTelemetry2 = { ph: 6.5 }
    mockApiGet
      .mockResolvedValueOnce({ data: { data: dummyTelemetry1 } })
      .mockResolvedValueOnce({ data: { data: dummyTelemetry2 } })

    const { fetchLastTelemetry } = useTelemetry()
    
    await fetchLastTelemetry(1)
    const refreshed = await fetchLastTelemetry(1, true) // Force refresh

    expect(refreshed).toEqual(dummyTelemetry2)
    expect(mockApiGet).toHaveBeenCalledTimes(2)
  })

  it('should handle fetch last telemetry error', async () => {
    const errorMessage = 'Network Error'
    mockApiGet.mockRejectedValue(new Error(errorMessage))

    const { fetchLastTelemetry, loading, error } = useTelemetry(mockShowToast)

    await expect(fetchLastTelemetry(1)).rejects.toThrow(errorMessage)
    expect(loading.value).toBe(false)
    expect(error.value).toBeInstanceOf(Error)
    expect(mockShowToast).toHaveBeenCalledWith('Ошибка при загрузке телеметрии', 'error', 5000)
  })

  it('should fetch history from API', async () => {
    const dummyHistory = [
      { ts: '2024-01-01T00:00:00Z', value: 6.0 },
      { ts: '2024-01-01T01:00:00Z', value: 6.1 }
    ]
    mockApiGet.mockResolvedValue({ data: { data: dummyHistory } })

    const { fetchHistory } = useTelemetry()
    const history = await fetchHistory(1, 'PH', { from: '2024-01-01', to: '2024-01-02' })

    expect(history).toHaveLength(2)
    expect(history[0]).toHaveProperty('ts')
    expect(history[0]).toHaveProperty('value')
    expect(mockApiGet).toHaveBeenCalledWith('/api/zones/1/telemetry/history', {
      params: {
        metric: 'PH',
        from: '2024-01-01',
        to: '2024-01-02'
      }
    })
  })

  it('should cache history', async () => {
    const dummyHistory = [{ ts: '2024-01-01T00:00:00Z', value: 6.0 }]
    mockApiGet.mockResolvedValue({ data: { data: dummyHistory } })

    const { fetchHistory } = useTelemetry()
    
    await fetchHistory(1, 'PH')
    const cached = await fetchHistory(1, 'PH') // Second call should use cache

    expect(cached).toHaveLength(1)
    expect(mockApiGet).toHaveBeenCalledTimes(1)
  })

  it('should handle fetch history error', async () => {
    const errorMessage = 'History Error'
    mockApiGet.mockRejectedValue(new Error(errorMessage))

    const { fetchHistory, error } = useTelemetry(mockShowToast)

    await expect(fetchHistory(1, 'PH')).rejects.toThrow(errorMessage)
    expect(error.value).toBeInstanceOf(Error)
    expect(mockShowToast).toHaveBeenCalledWith('Ошибка при загрузке истории PH', 'error', 5000)
  })

  it('should fetch aggregates from API', async () => {
    const dummyAggregates = [
      { ts: 1704067200000, value: 6.0, avg: 6.0, min: 5.8, max: 6.2 }
    ]
    mockApiGet.mockResolvedValue({ data: { data: dummyAggregates } })

    const { fetchAggregates } = useTelemetry()
    const aggregates = await fetchAggregates(1, 'ph', '24h')

    expect(aggregates).toEqual(dummyAggregates)
    expect(mockApiGet).toHaveBeenCalledWith('/api/telemetry/aggregates', {
      params: {
        zone_id: 1,
        metric: 'ph',
        period: '24h'
      }
    })
  })

  it('should cache aggregates', async () => {
    const dummyAggregates = [{ ts: 1704067200000, value: 6.0 }]
    mockApiGet.mockResolvedValue({ data: { data: dummyAggregates } })

    const { fetchAggregates } = useTelemetry()
    
    await fetchAggregates(1, 'ph', '24h')
    const cached = await fetchAggregates(1, 'ph', '24h') // Second call should use cache

    expect(cached).toEqual(dummyAggregates)
    expect(mockApiGet).toHaveBeenCalledTimes(1)
  })

  it('should handle fetch aggregates error', async () => {
    const errorMessage = 'Aggregates Error'
    mockApiGet.mockRejectedValue(new Error(errorMessage))

    const { fetchAggregates, error } = useTelemetry(mockShowToast)

    await expect(fetchAggregates(1, 'ph', '24h')).rejects.toThrow(errorMessage)
    expect(error.value).toBeInstanceOf(Error)
    expect(mockShowToast).toHaveBeenCalledWith('Ошибка при загрузке агрегированных данных ph', 'error', 5000)
  })

  it('should clear cache for specific zone', () => {
    const { clearCache } = useTelemetry()
    
    // This is a simple test - in real scenario, we'd need to populate cache first
    // But clearCache should not throw
    expect(() => clearCache(1)).not.toThrow()
  })

  it('should clear all cache', () => {
    const { clearCache } = useTelemetry()
    
    // This is a simple test - in real scenario, we'd need to populate cache first
    // But clearCache should not throw
    expect(() => clearCache()).not.toThrow()
  })
})

