import { defineStore } from 'pinia'
import type { Zone } from '@/types/Zone'

interface ZonesStoreState {
  items: Zone[]
}

interface InertiaPageProps {
  zones?: Zone[]
  [key: string]: unknown
}

export const useZonesStore = defineStore('zones', {
  state: (): ZonesStoreState => ({
    items: [] as Zone[],
  }),
  actions: {
    initFromProps(props: InertiaPageProps): void {
      if (props?.zones && Array.isArray(props.zones)) {
        this.items = props.zones
      }
    },
    upsert(zone: Zone): void {
      const idx = this.items.findIndex(z => z.id === zone.id)
      if (idx >= 0) {
        this.items[idx] = zone
      } else {
        this.items.push(zone)
      }
    },
    remove(zoneId: number): void {
      const idx = this.items.findIndex(z => z.id === zoneId)
      if (idx >= 0) {
        this.items.splice(idx, 1)
      }
    },
    clear(): void {
      this.items = []
    },
  },
  getters: {
    zoneById: (state) => {
      return (id: number): Zone | undefined => {
        return state.items.find(z => z.id === id)
      }
    },
    zonesByStatus: (state) => {
      return (status: Zone['status']): Zone[] => {
        return state.items.filter(z => z.status === status)
      }
    },
    zonesByGreenhouse: (state) => {
      return (greenhouseId: number): Zone[] => {
        return state.items.filter(z => z.greenhouse_id === greenhouseId)
      }
    },
  },
})

