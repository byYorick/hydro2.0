import { setActivePinia, createPinia } from 'pinia'
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
    expect(store.items).toEqual([])
  })

  it('should init from props', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    expect(store.items.length).toBe(1)
    expect(store.items[0]).toEqual(mockZone1)
  })

  it('should upsert existing zone', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    
    const updatedZone = { ...mockZone1, name: 'Zone 1 updated' }
    store.upsert(updatedZone)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].name).toBe('Zone 1 updated')
  })

  it('should add new zone on upsert', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1] })
    store.upsert(mockZone2)
    
    expect(store.items.length).toBe(2)
    expect(store.items[1]).toEqual(mockZone2)
  })

  it('should remove zone', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    store.remove(1)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].id).toBe(2)
  })

  it('should clear all zones', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [mockZone1, mockZone2] })
    
    store.clear()
    
    expect(store.items).toEqual([])
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
})

