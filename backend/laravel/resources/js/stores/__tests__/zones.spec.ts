import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useZonesStore } from '../zones'
import type { Zone } from '@/types/Zone'

describe('zones store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const mockZone1: Zone = {
    id: 1,
    uid: 'z-1',
    name: 'Zone 1',
    status: 'RUNNING',
    greenhouse_id: 1,
    targets: {
      ph_min: 5.5,
      ph_max: 6.5,
      ec_min: 1.0,
      ec_max: 2.0,
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  const mockZone2: Zone = {
    id: 2,
    uid: 'z-2',
    name: 'Zone 2',
    status: 'PAUSED',
    greenhouse_id: 1,
    targets: {
      ph_min: 5.5,
      ph_max: 6.5,
      ec_min: 1.0,
      ec_max: 2.0,
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  it('should initialize with empty items', () => {
    const store = useZonesStore()
    expect(store.items).toEqual({})
    expect(store.ids).toEqual([])
  })

  it('should init from props', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    expect(store.zonesCount).toBe(1)
    expect(store.zoneById(1)).toEqual(mockZone1)
  })

  it('should upsert existing zone', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    
    const updatedZone = { ...mockZone1, name: 'Zone 1 updated' }
    store.upsert(updatedZone)
    
    expect(store.zonesCount).toBe(1)
    expect(store.zoneById(1)?.name).toBe('Zone 1 updated')
  })

  it('should add new zone on upsert', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    store.upsert(mockZone2)
    
    expect(store.zonesCount).toBe(2)
    expect(store.zoneById(2)).toEqual(mockZone2)
  })

  it('should remove zone', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    store.remove(1)
    
    expect(store.zonesCount).toBe(1)
    expect(store.zoneById(2)?.id).toBe(2)
  })

  it('should clear all zones', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    store.clear()
    
    expect(store.items).toEqual({})
    expect(store.ids).toEqual([])
  })

  it('should get zone by id', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    const zone = store.zoneById(1)
    
    expect(zone).toEqual(mockZone1)
  })

  it('should get zones by status', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    const runningZones = store.zonesByStatus('RUNNING')
    
    expect(runningZones.length).toBe(1)
    expect(runningZones[0].status).toBe('RUNNING')
  })

  it('should get zones by greenhouse', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    const zones = store.zonesByGreenhouse(1)
    
    expect(zones.length).toBe(2)
  })

  it('should support optimistic updates', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    
    const originalZone = store.zoneById(1)
    const optimisticZone = { ...mockZone1, status: 'PAUSED' as const }
    
    // Оптимистичное обновление
    store.optimisticUpsert(optimisticZone)
    expect(store.zoneById(1)?.status).toBe('PAUSED')
    
    // Откат
    store.rollbackOptimisticUpdate(1, originalZone || null)
    expect(store.zoneById(1)?.status).toBe('RUNNING')
  })

  it('should track loading state', () => {
    const store = useZonesStore()
    
    expect(store.loading).toBe(false)
    
    store.setLoading(true)
    expect(store.loading).toBe(true)
    
    store.setLoading(false)
    expect(store.loading).toBe(false)
    expect(store.lastFetch).toBeInstanceOf(Date)
  })

  it('should track error state', () => {
    const store = useZonesStore()
    
    expect(store.error).toBe(null)
    
    store.setError('Test error')
    expect(store.error).toBe('Test error')
    
    store.setError(null)
    expect(store.error).toBe(null)
  })

  it('should invalidate cache', () => {
    const store = useZonesStore()
    const initialVersion = store.cacheVersion
    
    store.invalidateCache()
    
    expect(store.cacheVersion).toBe(initialVersion + 1)
    expect(store.cacheInvalidatedAt).toBeInstanceOf(Date)
  })

  it('should get all zones as array', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    const allZones = store.allZones
    
    expect(allZones.length).toBe(2)
    expect(allZones).toContainEqual(mockZone1)
    expect(allZones).toContainEqual(mockZone2)
  })

  it('should check if has zones', () => {
    const store = useZonesStore()
    
    expect(store.hasZones).toBe(false)
    
    store.initFromProps({ zones: [mockZone1] })
    expect(store.hasZones).toBe(true)
  })

  it('should get zones count', () => {
    const store = useZonesStore()
    
    expect(store.zonesCount).toBe(0)
    
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    expect(store.zonesCount).toBe(2)
  })

  it('should attach recipe with cross-store cache invalidation', async () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    
    const initialCacheVersion = store.cacheVersion
    
    // Мокаем recipes store
    vi.mock('../recipes', () => ({
      useRecipesStore: () => ({
        invalidateCache: vi.fn(),
      }),
    }))
    
    await store.attachRecipe(1, 10)
    
    expect(store.cacheVersion).toBeGreaterThan(initialCacheVersion)
  })

  it('should detach recipe with cross-store cache invalidation', async () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    
    const initialCacheVersion = store.cacheVersion
    
    // Мокаем recipes store
    vi.mock('../recipes', () => ({
      useRecipesStore: () => ({
        invalidateCache: vi.fn(),
      }),
    }))
    
    await store.detachRecipe(1, 10)
    
    expect(store.cacheVersion).toBeGreaterThan(initialCacheVersion)
  })
})

