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

export interface RecipeTargets {
  min?: number
  max?: number
  temperature?: number
  humidity?: number
  hours_on?: number
  hours_off?: number
  interval_minutes?: number
  duration_seconds?: number
  [key: string]: unknown
}

export interface SubsystemCycle {
  type: CycleType
  required: boolean
  strategy?: CycleStrategy | string
  interval?: number | null
  last_run?: string | null
  next_run?: string | null
  recipeTargets?: RecipeTargets | null
}

