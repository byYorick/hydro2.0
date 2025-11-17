import { defineStore } from 'pinia'

export const useDevicesStore = defineStore('devices', {
  state: () => ({
    items: [] as Array<any>,
  }),
  actions: {
    initFromProps(props: any) {
      if (props?.devices) this.items = props.devices
    },
    upsert(device: any) {
      const idx = this.items.findIndex(d => d.device_id === device.device_id)
      if (idx >= 0) this.items[idx] = device
      else this.items.push(device)
    },
  },
})

