import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useZones, clearZonesCache } from '../useZones'
import { api } from '@/services/api'

// Mock the typed API layer (services/api)
vi.mock('@/services/api', () => ({
  api: {
    zones: {
      list: vi.fn(),
      getById: vi.fn(),
    },
  },
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
    vi.mocked(api.zones.list).mockResolvedValue([{ id: 1, name: 'Zone 1' }] as never)

    const { fetchZones } = useZones()
    const zones = await fetchZones()

    expect(zones).toEqual([{ id: 1, name: 'Zone 1' }])
    expect(api.zones.list).toHaveBeenCalledTimes(1)
  })

  it('should cache zones', async () => {
    vi.mocked(api.zones.list).mockResolvedValue([{ id: 1, name: 'Zone 1' }] as never)

    const { fetchZones } = useZones()
    const zones1 = await fetchZones()
    const zones2 = await fetchZones() // Second call should use cache

    expect(zones1).toEqual(zones2)
    expect(api.zones.list).toHaveBeenCalledTimes(1) // Only called once due to cache
  })
})

