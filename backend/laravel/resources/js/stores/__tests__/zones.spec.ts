import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useZonesStore, shouldUpdateZone } from '../zones'
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
    
    // Обновляем зону с новым updated_at, чтобы zonesEqual определил изменение
    const updatedZone = { 
      ...mockZone1, 
      name: 'Zone 1 updated',
      updated_at: '2024-01-01T12:01:00Z' // Новый updated_at
    }
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

  describe('shouldUpdateZone function', () => {
    it('should return false for identical zones (same updated_at)', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(false)
    })

    it('should return true when updated_at differs', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:01:00Z',
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(true)
    })

    it('should return true when significant fields differ (name)', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1 Updated',
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(true)
    })

    it('should return true when significant fields differ (status)', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        status: 'RUNNING',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        status: 'PAUSED',
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(true)
    })

    it('should return true when targets differ', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        targets: {
          ph_min: 5.5,
          ph_max: 6.5,
          ec_min: 1.0,
          ec_max: 2.0,
        },
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        targets: {
          ph_min: 6.0,
          ph_max: 7.0,
          ec_min: 1.5,
          ec_max: 2.5,
        },
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(true)
    })

    it('should return false when only "noisy" fields differ (telemetry)', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
        telemetry: {
          ph: 6.0,
          ec: 1.5,
          temp: 25.0,
        },
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
        telemetry: {
          ph: 6.1,
          ec: 1.6,
          temp: 25.5,
        },
      }
      
      // updated_at одинаковый, значит не нужно обновлять
      expect(shouldUpdateZone(zone1, zone2)).toBe(false)
    })

    it('should return false when only devices array differs', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
        devices: [],
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
        devices: [{ id: 1 } as any],
      }
      
      // updated_at одинаковый, значит не нужно обновлять
      expect(shouldUpdateZone(zone1, zone2)).toBe(false)
    })

    it('should return false for identical zones without updated_at (fallback comparison)', () => {
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1',
        status: 'RUNNING',
        description: 'Test',
        greenhouse_id: 1,
        uid: 'z-1',
        targets: {
          ph_min: 5.5,
          ph_max: 6.5,
          ec_min: 1.0,
          ec_max: 2.0,
        },
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1',
        status: 'RUNNING',
        description: 'Test',
        greenhouse_id: 1,
        uid: 'z-1',
        targets: {
          ph_min: 5.5,
          ph_max: 6.5,
          ec_min: 1.0,
          ec_max: 2.0,
        },
      }
      
      expect(shouldUpdateZone(zone1, zone2)).toBe(false)
    })

    it('should return true for different IDs (different zones need update)', () => {
      const zone1: Zone = {
        ...mockZone1,
        id: 1,
      }
      const zone2: Zone = {
        ...mockZone2,
        id: 2,
      }
      
      // Разные ID - zonesEqual вернет false (разные зоны)
      // shouldUpdateZone вернет true (нужно обновить, так как это разные зоны)
      // На практике это не должно вызываться для разных ID в upsert,
      // но функция должна корректно обрабатывать этот случай
      expect(shouldUpdateZone(zone1, zone2)).toBe(true)
    })
  })

  describe('upsert without unnecessary mutations', () => {
    it('should not update store when zone is identical (same updated_at)', () => {
      const store = useZonesStore()
      const zone: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
      }
      
      store.upsert(zone)
      const firstCacheVersion = store.cacheVersion
      
      // Пытаемся обновить той же зоной
      store.upsert(zone)
      
      // cacheVersion не должен измениться
      expect(store.cacheVersion).toBe(firstCacheVersion)
    })

    it('should update store when zone changed (different updated_at)', () => {
      const store = useZonesStore()
      const zone1: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:00:00Z',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: '2024-01-01T12:01:00Z',
      }
      
      store.upsert(zone1)
      const firstCacheVersion = store.cacheVersion
      
      // Обновляем с новым updated_at
      store.upsert(zone2)
      
      // cacheVersion должен измениться
      expect(store.cacheVersion).toBeGreaterThan(firstCacheVersion)
      expect(store.zoneById(1)?.updated_at).toBe('2024-01-01T12:01:00Z')
    })

    it('should update store when significant fields change (without updated_at)', () => {
      const store = useZonesStore()
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1',
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        name: 'Zone 1 Updated',
      }
      
      store.upsert(zone1)
      const firstCacheVersion = store.cacheVersion
      
      // Обновляем с новым именем
      store.upsert(zone2)
      
      // cacheVersion должен измениться
      expect(store.cacheVersion).toBeGreaterThan(firstCacheVersion)
      expect(store.zoneById(1)?.name).toBe('Zone 1 Updated')
    })

    it('should update store when targets change (without updated_at)', () => {
      const store = useZonesStore()
      const zone1: Zone = {
        ...mockZone1,
        updated_at: undefined,
        targets: {
          ph_min: 5.5,
          ph_max: 6.5,
          ec_min: 1.0,
          ec_max: 2.0,
        },
      }
      const zone2: Zone = {
        ...mockZone1,
        updated_at: undefined,
        targets: {
          ph_min: 6.0,
          ph_max: 7.0,
          ec_min: 1.5,
          ec_max: 2.5,
        },
      }
      
      store.upsert(zone1)
      const firstCacheVersion = store.cacheVersion
      
      // Обновляем с новыми targets
      store.upsert(zone2)
      
      // cacheVersion должен измениться
      expect(store.cacheVersion).toBeGreaterThan(firstCacheVersion)
      expect(store.zoneById(1)?.targets.ph_min).toBe(6.0)
    })
  })
})

