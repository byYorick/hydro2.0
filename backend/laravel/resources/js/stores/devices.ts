import { defineStore } from 'pinia'
import type { Device } from '@/types/Device'
import { deviceEvents } from '@/composables/useStoreEvents'

interface DevicesStoreState {
  // Нормализованная структура: Record<id, Device> для быстрого доступа O(1)
  items: Record<number | string, Device>
  // Массив идентификаторов для сохранения порядка
  ids: Array<number | string>
  
  // Состояние загрузки
  loading: boolean
  error: string | null
  lastFetch: Date | null
  
  // Инвалидация кеша
  cacheVersion: number
  cacheInvalidatedAt: Date | null
}

interface InertiaPageProps {
  devices?: Device[]
  [key: string]: unknown
}

export const useDevicesStore = defineStore('devices', {
  state: (): DevicesStoreState => ({
    items: {} as Record<number | string, Device>,
    ids: [] as Array<number | string>,
    loading: false,
    error: null,
    lastFetch: null,
    cacheVersion: 0,
    cacheInvalidatedAt: null,
  }),
  actions: {
    initFromProps(props: InertiaPageProps): void {
      if (props?.devices && Array.isArray(props.devices)) {
        this.setDevices(props.devices)
      }
    },
    
    /**
     * Установить устройства (нормализация в Record)
     */
    setDevices(devices: Device[]): void {
      const normalized: Record<number | string, Device> = {}
      const ids: Array<number | string> = []
      
      devices.forEach(device => {
        const identifier = device.id || device.uid
        if (identifier) {
          normalized[identifier] = device
          ids.push(identifier)
        }
      })
      
      this.items = normalized
      this.ids = ids
      this.lastFetch = new Date()
      this.cacheVersion++
    },
    
    /**
     * Добавить или обновить устройство
     */
    upsert(device: Device): void {
      const identifier = device.id || device.uid
      if (!identifier) return
      
      const oldDevice = this.items[identifier]
      const exists = !!oldDevice
      
      this.items[identifier] = device
      
      if (!exists) {
        this.ids.push(identifier)
        // Эмитим событие создания
        deviceEvents.created(device)
      } else {
        // Эмитим событие обновления
        deviceEvents.updated(device)
        
        // Если изменилось lifecycle состояние, эмитим специальное событие
        if (oldDevice.lifecycle_state !== device.lifecycle_state && device.lifecycle_state) {
          deviceEvents.lifecycleTransitioned({
            deviceId: typeof identifier === 'number' ? identifier : 0,
            fromState: oldDevice.lifecycle_state || 'UNKNOWN',
            toState: device.lifecycle_state,
          })
        }
      }
      
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Удалить устройство
     */
    remove(deviceId: number | string): void {
      if (this.items[deviceId]) {
        delete this.items[deviceId]
        this.ids = this.ids.filter(id => id !== deviceId)
        
        // Эмитим событие удаления
        deviceEvents.deleted(deviceId)
        
        this.cacheVersion++
        this.cacheInvalidatedAt = new Date()
      }
    },
    
    /**
     * Очистить все устройства
     */
    clear(): void {
      this.items = {}
      this.ids = []
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Инвалидировать кеш (для принудительного обновления)
     */
    invalidateCache(): void {
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Установить состояние загрузки
     */
    setLoading(loading: boolean): void {
      this.loading = loading
      if (!loading) {
        this.lastFetch = new Date()
      }
    },
    
    /**
     * Установить ошибку
     */
    setError(error: string | null): void {
      this.error = error
    },
    
    /**
     * Оптимистичное обновление устройства (без эмиссии событий)
     * Используется для временных изменений перед подтверждением сервером
     */
    optimisticUpsert(device: Device): void {
      const identifier = device.id || device.uid
      if (!identifier) return
      
      const exists = this.items[identifier]
      this.items[identifier] = device
      
      if (!exists) {
        this.ids.push(identifier)
      }
      
      // Не инвалидируем кеш и не эмитим события для оптимистичных обновлений
      // Это делается после подтверждения сервером
    },
    
    /**
     * Откатить оптимистичное обновление устройства
     */
    rollbackOptimisticUpdate(deviceId: number | string, originalDevice: Device | null): void {
      if (originalDevice) {
        // Восстанавливаем исходное состояние
        const identifier = originalDevice.id || originalDevice.uid || deviceId
        this.items[identifier] = originalDevice
      } else {
        // Если устройства не было, удаляем его
        if (this.items[deviceId]) {
          delete this.items[deviceId]
          this.ids = this.ids.filter(id => id !== deviceId)
        }
      }
    },
  },
  getters: {
    /**
     * Получить устройство по ID или UID (O(1) вместо O(n))
     */
    deviceById: (state) => {
      return (id: number | string): Device | undefined => {
        return state.items[id]
      }
    },
    
    /**
     * Получить все устройства как массив (в порядке ids)
     */
    allDevices: (state): Device[] => {
      return state.ids.map(id => state.items[id]).filter(Boolean)
    },
    
    /**
     * Устройства по типу
     */
    devicesByType: (state) => {
      return (type: Device['type']): Device[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(device => device?.type === type)
      }
    },
    
    /**
     * Устройства по статусу
     */
    devicesByStatus: (state) => {
      return (status: Device['status']): Device[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(device => device?.status === status)
      }
    },
    
    /**
     * Устройства по зоне
     */
    devicesByZone: (state) => {
      return (zoneId: number): Device[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(device => device?.zone_id === zoneId)
      }
    },
    
    /**
     * Устройства по lifecycle состоянию
     */
    devicesByLifecycleState: (state) => {
      return (lifecycleState: string): Device[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(device => device?.lifecycle_state === lifecycleState)
      }
    },
    
    /**
     * Проверка, есть ли устройства в store
     */
    hasDevices: (state): boolean => {
      return state.ids.length > 0
    },
    
    /**
     * Количество устройств
     */
    devicesCount: (state): number => {
      return state.ids.length
    },
  },
})

