/**
 * Тип цикла
 */
export type CycleType = 'PH_CONTROL' | 'EC_CONTROL' | 'IRRIGATION' | 'LIGHTING' | 'CLIMATE'

/**
 * Стратегия цикла
 */
export type CycleStrategy = 'periodic' | 'on_demand' | 'scheduled'

/**
 * Модель цикла
 */
export interface Cycle {
  type: CycleType
  strategy?: CycleStrategy
  interval?: number | null
  last_run?: string | null
  next_run?: string | null
  created_at?: string
  updated_at?: string
}

