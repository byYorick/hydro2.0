import { defineStore } from 'pinia'

export const useAlertsStore = defineStore('alerts', {
  state: () => ({
    items: [] as Array<any>,
  }),
  actions: {
    setAll(list: Array<any>) {
      this.items = Array.isArray(list) ? list : []
    },
    upsert(alert: any) {
      const idx = this.items.findIndex(a => a.id === alert.id)
      if (idx >= 0) this.items[idx] = alert
      else this.items.unshift(alert)
    },
    setResolved(id: string | number) {
      const idx = this.items.findIndex(a => a.id === id)
      if (idx >= 0) this.items[idx] = { ...this.items[idx], resolved: true }
    },
  },
})

