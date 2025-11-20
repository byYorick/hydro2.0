import { setActivePinia, createPinia } from 'pinia'
import { useDevicesStore } from '../devices'
import type { Device } from '@/types/Device'

describe('devices store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const mockDevice1: Device = {
    id: 1,
    uid: 'device-1',
    name: 'Device 1',
    type: 'sensor',
    status: 'online',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  const mockDevice2: Device = {
    id: 2,
    uid: 'device-2',
    name: 'Device 2',
    type: 'actuator',
    status: 'offline',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  it('should initialize with empty items', () => {
    const store = useDevicesStore()
    expect(store.items).toEqual([])
  })

  it('should init from props', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1] })
    expect(store.items.length).toBe(1)
    expect(store.items[0]).toEqual(mockDevice1)
  })

  it('should upsert existing device by id', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1] })
    
    const updatedDevice = { ...mockDevice1, name: 'Device 1 updated' }
    store.upsert(updatedDevice)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].name).toBe('Device 1 updated')
  })

  it('should add new device on upsert', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1] })
    store.upsert(mockDevice2)
    
    expect(store.items.length).toBe(2)
    expect(store.items[1]).toEqual(mockDevice2)
  })

  it('should remove device by id', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    store.remove(1)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].id).toBe(2)
  })

  it('should remove device by uid', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    store.remove('device-1')
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].uid).toBe('device-2')
  })

  it('should clear all devices', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    store.clear()
    
    expect(store.items).toEqual([])
  })

  it('should get device by id', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    const device = store.deviceById(1)
    
    expect(device).toEqual(mockDevice1)
  })

  it('should get device by uid', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    const device = store.deviceById('device-1')
    
    expect(device).toEqual(mockDevice1)
  })

  it('should get devices by type', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    const sensors = store.devicesByType('sensor')
    
    expect(sensors.length).toBe(1)
    expect(sensors[0].type).toBe('sensor')
  })

  it('should get devices by status', () => {
    const store = useDevicesStore()
    store.initFromProps({ devices: [mockDevice1, mockDevice2] })
    
    const onlineDevices = store.devicesByStatus('online')
    
    expect(onlineDevices.length).toBe(1)
    expect(onlineDevices[0].status).toBe('online')
  })

  it('should get devices by zone', () => {
    const store = useDevicesStore()
    const deviceWithZone = { ...mockDevice1, zone_id: 1 }
    store.initFromProps({ devices: [deviceWithZone, mockDevice2] })
    
    const zoneDevices = store.devicesByZone(1)
    
    expect(zoneDevices.length).toBe(1)
    expect(zoneDevices[0].zone_id).toBe(1)
  })
})

