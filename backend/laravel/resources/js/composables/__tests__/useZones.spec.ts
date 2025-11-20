import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useZones, clearZonesCache } from '../useZones'

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

describe('useZones', () => {
  beforeEach(() => {
    clearZonesCache() // Очищаем кеш перед каждым тестом
    vi.clearAllMocks()
  })

  it('should initialize with loading false', () => {
    const { loading } = useZones()
    expect(loading.value).toBe(false)
  })

  it('should fetch zones from API', async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        get: vi.fn().mockResolvedValue({
          data: { data: [{ id: 1, name: 'Zone 1' }] }
        })
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)

    const { fetchZones } = useZones()
    const zones = await fetchZones()

    expect(zones).toEqual([{ id: 1, name: 'Zone 1' }])
    expect(mockApi.api.get).toHaveBeenCalledWith('/api/zones')
  })

  it('should cache zones', async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        get: vi.fn().mockResolvedValue({
          data: { data: [{ id: 1, name: 'Zone 1' }] }
        })
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)

    const { fetchZones } = useZones()
    const zones1 = await fetchZones()
    const zones2 = await fetchZones() // Second call should use cache

    expect(zones1).toEqual(zones2)
    expect(mockApi.api.get).toHaveBeenCalledTimes(1) // Only called once due to cache
  })
})

