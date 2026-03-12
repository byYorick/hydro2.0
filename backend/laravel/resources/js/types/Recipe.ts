import type { Zone } from './Zone'

/**
 * Цели фазы рецепта
 */
export interface RecipePhaseTargets {
  ph?: {
    min: number
    max: number
  }
  ec?: {
    min: number
    max: number
  }
}

/**
 * Фаза рецепта
 */
export interface RecipePhase {
  id: number
  phase_index: number
  name: string
  duration_hours: number
  targets?: RecipePhaseTargets
  created_at?: string
  updated_at?: string
}

/**
 * Модель рецепта
 */
export interface Recipe {
  id: number
  name: string
  description?: string
  phases?: RecipePhase[]
  phases_count?: number
  created_at?: string
  updated_at?: string
}

/**
 * Экземпляр рецепта (применённый к зоне)
 */
export interface RecipeInstance {
  id: number
  recipe_id: number
  recipe?: Recipe
  zone_id: number
  zone?: Zone
  current_phase_index: number | null
  started_at?: string
  created_at?: string
  updated_at?: string
}

