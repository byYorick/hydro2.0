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
  temp_air?: number
  humidity_air?: number
  light_hours?: number
  irrigation_interval_sec?: number
  irrigation_duration_sec?: number
}

export interface NutrientProduct {
  id: number
  manufacturer: string
  name: string
  component: 'npk' | 'calcium' | 'magnesium' | 'micro'
  composition?: string | null
  recommended_stage?: string | null
  notes?: string | null
  metadata?: Record<string, any> | null
  created_at?: string
  updated_at?: string
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
  nutrient_program_code?: string | null
  nutrient_mode?: 'ratio_ec_pid' | 'delta_ec_by_k' | 'dose_ml_l_only' | null
  nutrient_npk_ratio_pct?: number | string | null
  nutrient_calcium_ratio_pct?: number | string | null
  nutrient_magnesium_ratio_pct?: number | string | null
  nutrient_micro_ratio_pct?: number | string | null
  nutrient_npk_dose_ml_l?: number | string | null
  nutrient_calcium_dose_ml_l?: number | string | null
  nutrient_magnesium_dose_ml_l?: number | string | null
  nutrient_micro_dose_ml_l?: number | string | null
  nutrient_npk_product_id?: number | null
  nutrient_calcium_product_id?: number | null
  nutrient_magnesium_product_id?: number | null
  nutrient_micro_product_id?: number | null
  nutrient_dose_delay_sec?: number | null
  nutrient_ec_stop_tolerance?: number | string | null
  nutrient_solution_volume_l?: number | string | null
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
  latest_published_revision_id?: number | null
  latest_draft_revision_id?: number | null
  plants?: Array<{ id: number; name: string }>
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
