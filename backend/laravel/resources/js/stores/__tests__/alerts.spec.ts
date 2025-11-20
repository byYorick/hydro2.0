import { setActivePinia, createPinia } from 'pinia'
import { useAlertsStore } from '../alerts'
import type { Alert } from '@/types/Alert'

describe('alerts store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const mockAlert1: Alert = {
    id: 1,
    type: 'PH_HIGH',
    status: 'active',
    message: 'pH too high',
    zone_id: 1,
    created_at: '2024-01-01T00:00:00Z',
  }

  const mockAlert2: Alert = {
    id: 2,
    type: 'EC_LOW',
    status: 'resolved',
    message: 'EC too low',
    zone_id: 1,
    created_at: '2024-01-01T00:00:00Z',
    resolved_at: '2024-01-01T01:00:00Z',
  }

  it('should initialize with empty items', () => {
    const store = useAlertsStore()
    expect(store.items).toEqual([])
  })

  it('should set all alerts', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    expect(store.items.length).toBe(2)
  })

  it('should upsert existing alert', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1])
    
    const updatedAlert = { ...mockAlert1, message: 'Updated message' }
    store.upsert(updatedAlert)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].message).toBe('Updated message')
  })

  it('should add new alert at beginning on upsert', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1])
    store.upsert(mockAlert2)
    
    expect(store.items.length).toBe(2)
    expect(store.items[0]).toEqual(mockAlert2) // Should be at the beginning
  })

  it('should set alert as resolved', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1])
    
    store.setResolved(1)
    
    expect(store.items[0].status).toBe('resolved')
    expect(store.items[0].resolved_at).toBeDefined()
  })

  it('should remove alert', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    store.remove(1)
    
    expect(store.items.length).toBe(1)
    expect(store.items[0].id).toBe(2)
  })

  it('should clear all alerts', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    store.clear()
    
    expect(store.items).toEqual([])
  })

  it('should get alert by id', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    const alert = store.alertById(1)
    
    expect(alert).toEqual(mockAlert1)
  })

  it('should get active alerts', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    const activeAlerts = store.activeAlerts
    
    expect(activeAlerts.length).toBe(1)
    expect(activeAlerts[0].status).toBe('active')
  })

  it('should get resolved alerts', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    const resolvedAlerts = store.resolvedAlerts
    
    expect(resolvedAlerts.length).toBe(1)
    expect(resolvedAlerts[0].status).toBe('resolved')
  })

  it('should get alerts by zone', () => {
    const store = useAlertsStore()
    const alert3 = { ...mockAlert2, id: 3, zone_id: 2 }
    store.setAll([mockAlert1, mockAlert2, alert3])
    
    const zoneAlerts = store.alertsByZone(1)
    
    expect(zoneAlerts.length).toBe(2)
    expect(zoneAlerts.every(a => a.zone_id === 1)).toBe(true)
  })

  it('should get alerts by type', () => {
    const store = useAlertsStore()
    store.setAll([mockAlert1, mockAlert2])
    
    const phAlerts = store.alertsByType('PH_HIGH')
    
    expect(phAlerts.length).toBe(1)
    expect(phAlerts[0].type).toBe('PH_HIGH')
  })
})

