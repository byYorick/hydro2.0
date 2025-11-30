import { defineStore } from 'pinia'
import type { Zone } from '@/types/Zone'
import { zoneEvents } from '@/composables/useStoreEvents'

interface ZonesStoreState {
  // Нормализованная структура: Record<id, Zone> для быстрого доступа O(1)
  items: Record<number, Zone>
  // Массив ID для сохранения порядка
  ids: number[]
  
  // Состояние загрузки
  loading: boolean
  error: string | null
  lastFetch: Date | null
  
  // Инвалидация кеша
  cacheVersion: number
  cacheInvalidatedAt: Date | null
}

interface InertiaPageProps {
  zones?: Zone[]
  [key: string]: unknown
}

export const useZonesStore = defineStore('zones', {
  state: (): ZonesStoreState => ({
    items: {} as Record<number, Zone>,
    ids: [] as number[],
    loading: false,
    error: null,
    lastFetch: null,
    cacheVersion: 0,
    cacheInvalidatedAt: null,
  }),
  actions: {
    initFromProps(props: InertiaPageProps): void {
      if (props?.zones && Array.isArray(props.zones)) {
        this.setZones(props.zones)
      }
    },
    
    /**
     * Установить зоны (нормализация в Record)
     */
    setZones(zones: Zone[]): void {
      const normalized: Record<number, Zone> = {}
      const ids: number[] = []
      
      zones.forEach(zone => {
        if (zone.id) {
          normalized[zone.id] = zone
          ids.push(zone.id)
        }
      })
      
      this.items = normalized
      this.ids = ids
      this.lastFetch = new Date()
      this.cacheVersion++
    },
    
    /**
     * Добавить или обновить зону
     * @param zone - зона для добавления/обновления
     * @param silent - если true, не эмитит события (для предотвращения рекурсии)
     */
    upsert(zone: Zone, silent: boolean = false): void {
      if (!zone.id) return
      
      const exists = this.items[zone.id]
      
      // Проверяем, изменилась ли зона (простое сравнение по JSON)
      // Это предотвращает рекурсию при обновлении с теми же данными
      if (exists) {
        const existingJson = JSON.stringify(exists)
        const newJson = JSON.stringify(zone)
        if (existingJson === newJson) {
          // Данные не изменились, не обновляем и не эмитим события
          return
        }
      }
      
      this.items[zone.id] = zone
      
      if (!exists) {
        this.ids.push(zone.id)
        // Эмитим событие создания только если не silent
        if (!silent) {
          zoneEvents.created(zone)
        }
      } else {
        // Эмитим событие обновления только если не silent
        if (!silent) {
          zoneEvents.updated(zone)
        }
      }
      
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Удалить зону
     */
    remove(zoneId: number): void {
      if (this.items[zoneId]) {
        delete this.items[zoneId]
        this.ids = this.ids.filter(id => id !== zoneId)
        
        // Эмитим событие удаления
        zoneEvents.deleted(zoneId)
        
        this.cacheVersion++
        this.cacheInvalidatedAt = new Date()
      }
    },
    
    /**
     * Очистить все зоны
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
     * Присвоить рецепт к зоне с перекрестной инвалидацией кеша
     */
    async attachRecipe(zoneId: number, recipeId: number): Promise<void> {
      const { useRecipesStore } = await import('./recipes')
      const recipesStore = useRecipesStore()
      
      // Инвалидируем кеш зон и рецептов
      this.invalidateCache()
      recipesStore.invalidateCache()
      
      // Уведомляем другие экраны через события
      zoneEvents.recipeAttached({ zoneId, recipeId })
    },
    
    /**
     * Отсоединить рецепт от зоны с перекрестной инвалидацией кеша
     */
    async detachRecipe(zoneId: number, recipeId: number): Promise<void> {
      const { useRecipesStore } = await import('./recipes')
      const recipesStore = useRecipesStore()
      
      // Инвалидируем кеш зон и рецептов
      this.invalidateCache()
      recipesStore.invalidateCache()
      
      // Уведомляем другие экраны через события
      zoneEvents.recipeDetached({ zoneId, recipeId })
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
     * Оптимистичное обновление зоны (без эмиссии событий)
     * Используется для временных изменений перед подтверждением сервером
     */
    optimisticUpsert(zone: Zone): void {
      if (!zone.id) return
      
      const exists = this.items[zone.id]
      this.items[zone.id] = zone
      
      if (!exists) {
        this.ids.push(zone.id)
      }
      
      // Не инвалидируем кеш и не эмитим события для оптимистичных обновлений
      // Это делается после подтверждения сервером
    },
    
    /**
     * Откатить оптимистичное обновление зоны
     */
    rollbackOptimisticUpdate(zoneId: number, originalZone: Zone | null): void {
      if (originalZone) {
        // Восстанавливаем исходное состояние
        this.items[zoneId] = originalZone
      } else {
        // Если зоны не было, удаляем её
        if (this.items[zoneId]) {
          delete this.items[zoneId]
          this.ids = this.ids.filter(id => id !== zoneId)
        }
      }
    },
  },
  getters: {
    /**
     * Получить зону по ID (O(1) вместо O(n))
     */
    zoneById: (state) => {
      return (id: number): Zone | undefined => {
        return state.items[id]
      }
    },
    
    /**
     * Получить все зоны как массив (в порядке ids)
     */
    allZones: (state): Zone[] => {
      return state.ids.map(id => state.items[id]).filter(Boolean)
    },
    
    /**
     * Зоны по статусу
     */
    zonesByStatus: (state) => {
      return (status: Zone['status']): Zone[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(zone => zone?.status === status)
      }
    },
    
    /**
     * Зоны по теплице
     */
    zonesByGreenhouse: (state) => {
      return (greenhouseId: number): Zone[] => {
        return state.ids
          .map(id => state.items[id])
          .filter(zone => zone?.greenhouse_id === greenhouseId)
      }
    },
    
    /**
     * Проверка, есть ли зоны в store
     */
    hasZones: (state): boolean => {
      return state.ids.length > 0
    },
    
    /**
     * Количество зон
     */
    zonesCount: (state): number => {
      return state.ids.length
    },
  },
})

