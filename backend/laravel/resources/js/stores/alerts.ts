import { defineStore } from 'pinia'
import type { Alert, AlertStatus } from '@/types/Alert'

interface AlertsStoreState {
  items: Alert[]
}

export const useAlertsStore = defineStore('alerts', {
  state: (): AlertsStoreState => ({
    items: [] as Alert[],
  }),
  actions: {
    setAll(list: Alert[]): void {
      this.items = Array.isArray(list) ? list : []
    },
    upsert(alert: Alert): void {
      const idx = this.items.findIndex(a => a.id === alert.id)
      if (idx >= 0) {
        this.items[idx] = alert
      } else {
        this.items.unshift(alert)
      }
    },
    setResolved(id: number): void {
      const idx = this.items.findIndex(a => a.id === id)
      if (idx >= 0) {
        this.items[idx] = {
          ...this.items[idx],
          status: 'resolved' as AlertStatus,
          resolved_at: new Date().toISOString(),
        }
      }
    },
    remove(id: number): void {
      const idx = this.items.findIndex(a => a.id === id)
      if (idx >= 0) {
        this.items.splice(idx, 1)
      }
    },
    clear(): void {
      this.items = []
    },
  },
  getters: {
    alertById: (state) => {
      return (id: number): Alert | undefined => {
        return state.items.find(a => a.id === id)
      }
    },
    activeAlerts: (state): Alert[] => {
      return state.items.filter(a => a.status === 'active' || a.status === 'ACTIVE')
    },
    resolvedAlerts: (state): Alert[] => {
      return state.items.filter(a => a.status === 'resolved' || a.status === 'RESOLVED')
    },
    alertsByZone: (state) => {
      return (zoneId: number): Alert[] => {
        return state.items.filter(a => a.zone_id === zoneId)
      }
    },
    alertsByType: (state) => {
      return (type: Alert['type']): Alert[] => {
        return state.items.filter(a => a.type === type)
      }
    },
  },
})

