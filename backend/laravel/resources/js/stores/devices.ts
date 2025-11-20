import { defineStore } from 'pinia'
import type { Device } from '@/types/Device'

interface DevicesStoreState {
  items: Device[]
}

interface InertiaPageProps {
  devices?: Device[]
  [key: string]: unknown
}

export const useDevicesStore = defineStore('devices', {
  state: (): DevicesStoreState => ({
    items: [] as Device[],
  }),
  actions: {
    initFromProps(props: InertiaPageProps): void {
      if (props?.devices && Array.isArray(props.devices)) {
        this.items = props.devices
      }
    },
    upsert(device: Device): void {
      // Используем id или uid для поиска
      const identifier = device.id || device.uid
      const idx = this.items.findIndex(d => (d.id || d.uid) === identifier)
      if (idx >= 0) {
        this.items[idx] = device
      } else {
        this.items.push(device)
      }
    },
    remove(deviceId: number | string): void {
      const idx = this.items.findIndex(d => d.id === deviceId || d.uid === deviceId)
      if (idx >= 0) {
        this.items.splice(idx, 1)
      }
    },
    clear(): void {
      this.items = []
    },
  },
  getters: {
    deviceById: (state) => {
      return (id: number | string): Device | undefined => {
        return state.items.find(d => d.id === id || d.uid === id)
      }
    },
    devicesByType: (state) => {
      return (type: Device['type']): Device[] => {
        return state.items.filter(d => d.type === type)
      }
    },
    devicesByStatus: (state) => {
      return (status: Device['status']): Device[] => {
        return state.items.filter(d => d.status === status)
      }
    },
    devicesByZone: (state) => {
      return (zoneId: number): Device[] => {
        return state.items.filter(d => d.zone_id === zoneId)
      }
    },
  },
})

