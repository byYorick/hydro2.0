import { defineStore } from 'pinia'
import type { GrowCycle } from '@/types/GrowCycle'

/**
 * Store для управления циклами выращивания
 * 
 * Нормализованная структура данных:
 * - items: Record<cycleId, GrowCycle> - все циклы по ID
 * - activeByZone: Record<zoneId, cycleId> - активный цикл для каждой зоны
 * 
 * Это позволяет быстро находить активный цикл для зоны (O(1))
 * и избежать дублирования данных
 */
interface CyclesStoreState {
  // Нормализованная структура: Record<id, GrowCycle> для быстрого доступа O(1)
  items: Record<number, GrowCycle>
  
  // Маппинг активных циклов по зонам: Record<zoneId, cycleId>
  // Это позволяет быстро найти активный цикл для зоны без перебора всех циклов
  activeByZone: Record<number, number>
  
  // Состояние загрузки
  loading: boolean
  error: string | null
  lastFetch: Date | null
  
  // Инвалидация кеша
  cacheVersion: number
  cacheInvalidatedAt: Date | null
}

/**
 * Определяет, является ли цикл активным (RUNNING или PAUSED)
 */
function isActiveCycle(cycle: GrowCycle): boolean {
  return cycle.status === 'RUNNING' || cycle.status === 'PAUSED'
}

/**
 * Определяет, нужно ли обновлять цикл в store
 * Использует updated_at для определения изменений
 */
function shouldUpdateCycle(existing: GrowCycle, incoming: GrowCycle): boolean {
  if (existing.id !== incoming.id) {
    return false
  }
  
  // Используем updated_at для определения изменений
  if (existing.updated_at && incoming.updated_at) {
    return existing.updated_at !== incoming.updated_at
  }
  
  // Fallback: сравниваем статус и важные поля
  return (
    existing.status !== incoming.status ||
    existing.current_phase_index !== incoming.current_phase_index ||
    existing.started_at !== incoming.started_at ||
    existing.paused_at !== incoming.paused_at ||
    existing.completed_at !== incoming.completed_at ||
    existing.aborted_at !== incoming.aborted_at ||
    existing.harvested_at !== incoming.harvested_at
  )
}

export const useCyclesStore = defineStore('cycles', {
  state: (): CyclesStoreState => ({
    items: {},
    activeByZone: {},
    loading: false,
    error: null,
    lastFetch: null,
    cacheVersion: 0,
    cacheInvalidatedAt: null,
  }),

  getters: {
    /**
     * Получить цикл по ID
     */
    cycleById: (state) => {
      return (id: number): GrowCycle | undefined => {
        return state.items[id]
      }
    },

    /**
     * Получить активный цикл для зоны
     * Это основной геттер для использования в компонентах
     */
    activeCycleByZone: (state) => {
      return (zoneId: number): GrowCycle | undefined => {
        const cycleId = state.activeByZone[zoneId]
        if (!cycleId) {
          return undefined
        }
        return state.items[cycleId]
      }
    },

    /**
     * Получить все активные циклы
     */
    activeCycles: (state): GrowCycle[] => {
      return Object.values(state.items).filter(isActiveCycle)
    },

    /**
     * Получить все циклы для зоны
     */
    cyclesByZone: (state) => {
      return (zoneId: number): GrowCycle[] => {
        return Object.values(state.items).filter(cycle => cycle.zone_id === zoneId)
      }
    },

    /**
     * Получить циклы по статусу
     */
    cyclesByStatus: (state) => {
      return (status: GrowCycle['status']): GrowCycle[] => {
        return Object.values(state.items).filter(cycle => cycle.status === status)
      }
    },

    /**
     * Проверить, есть ли активный цикл для зоны
     */
    hasActiveCycle: (state) => {
      return (zoneId: number): boolean => {
        const cycleId = state.activeByZone[zoneId]
        if (!cycleId) {
          return false
        }
        const cycle = state.items[cycleId]
        return cycle ? isActiveCycle(cycle) : false
      }
    },
  },

  actions: {
    /**
     * Установить все циклы (при загрузке из API)
     */
    setAll(cycles: GrowCycle[]): void {
      const normalized: Record<number, GrowCycle> = {}
      const activeByZone: Record<number, number> = {}

      for (const cycle of cycles) {
        normalized[cycle.id] = cycle
        
        // Обновляем маппинг активных циклов
        if (isActiveCycle(cycle)) {
          // Если для зоны уже есть активный цикл, выбираем более новый
          const existingCycleId = activeByZone[cycle.zone_id]
          if (existingCycleId) {
            const existingCycle = normalized[existingCycleId]
            if (existingCycle && existingCycle.started_at && cycle.started_at) {
              // Выбираем цикл с более поздней датой начала
              if (new Date(cycle.started_at) > new Date(existingCycle.started_at)) {
                activeByZone[cycle.zone_id] = cycle.id
              }
            } else {
              // Если нет дат начала, выбираем более новый по updated_at
              if (existingCycle && existingCycle.updated_at && cycle.updated_at) {
                if (new Date(cycle.updated_at) > new Date(existingCycle.updated_at)) {
                  activeByZone[cycle.zone_id] = cycle.id
                }
              } else {
                // По умолчанию используем новый цикл
                activeByZone[cycle.zone_id] = cycle.id
              }
            }
          } else {
            activeByZone[cycle.zone_id] = cycle.id
          }
        }
      }

      this.items = normalized
      this.activeByZone = activeByZone
      this.lastFetch = new Date()
      this.cacheVersion++
    },

    /**
     * Добавить или обновить цикл
     */
    upsert(cycle: GrowCycle): void {
      const existing = this.items[cycle.id]
      
      // Обновляем только если данные изменились
      if (!existing || shouldUpdateCycle(existing, cycle)) {
        this.items[cycle.id] = cycle
        
        // Обновляем маппинг активных циклов
        if (isActiveCycle(cycle)) {
          const existingCycleId = this.activeByZone[cycle.zone_id]
          
          // Если для зоны уже есть активный цикл
          if (existingCycleId && existingCycleId !== cycle.id) {
            const existingCycle = this.items[existingCycleId]
            if (existingCycle && existingCycle.started_at && cycle.started_at) {
              // Выбираем цикл с более поздней датой начала
              if (new Date(cycle.started_at) > new Date(existingCycle.started_at)) {
                this.activeByZone[cycle.zone_id] = cycle.id
              }
            } else {
              // По умолчанию используем новый цикл
              this.activeByZone[cycle.zone_id] = cycle.id
            }
          } else {
            this.activeByZone[cycle.zone_id] = cycle.id
          }
        } else {
          // Если цикл больше не активен, удаляем из маппинга
          if (this.activeByZone[cycle.zone_id] === cycle.id) {
            delete this.activeByZone[cycle.zone_id]
            
            // Ищем другой активный цикл для этой зоны
            const otherActiveCycle = Object.values(this.items).find(
              c => c.zone_id === cycle.zone_id && isActiveCycle(c) && c.id !== cycle.id
            )
            if (otherActiveCycle) {
              this.activeByZone[cycle.zone_id] = otherActiveCycle.id
            }
          }
        }
        
        this.cacheVersion++
      }
    },

    /**
     * Удалить цикл
     */
    remove(id: number): void {
      const cycle = this.items[id]
      if (cycle) {
        // Удаляем из маппинга активных циклов
        if (this.activeByZone[cycle.zone_id] === id) {
          delete this.activeByZone[cycle.zone_id]
          
          // Ищем другой активный цикл для этой зоны
          const otherActiveCycle = Object.values(this.items).find(
            c => c.zone_id === cycle.zone_id && isActiveCycle(c) && c.id !== id
          )
          if (otherActiveCycle) {
            this.activeByZone[cycle.zone_id] = otherActiveCycle.id
          }
        }
        
        delete this.items[id]
        this.cacheVersion++
      }
    },

    /**
     * Очистить все циклы
     */
    clear(): void {
      this.items = {}
      this.activeByZone = {}
      this.cacheVersion++
    },

    /**
     * Инвалидировать кеш
     */
    invalidateCache(): void {
      this.cacheInvalidatedAt = new Date()
      this.cacheVersion++
    },

    /**
     * Установить состояние загрузки
     */
    setLoading(loading: boolean): void {
      this.loading = loading
    },

    /**
     * Установить ошибку
     */
    setError(error: string | null): void {
      this.error = error
    },
  },
})


