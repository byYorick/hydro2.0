import { defineStore } from 'pinia'

export const useZonesStore = defineStore('zones', {
  state: () => ({
    items: [] as Array<any>,
  }),
  actions: {
    initFromProps(props: any) {
      if (props?.zones) this.items = props.zones
    },
    upsert(zone: any) {
      const idx = this.items.findIndex(z => z.id === zone.id)
      if (idx >= 0) this.items[idx] = zone
      else this.items.push(zone)
    },
  },
})

