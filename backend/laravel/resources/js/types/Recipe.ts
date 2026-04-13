import type { Zone } from './Zone'

/**
 * Цели фазы рецепта
 */
export interface RecipePhaseTargets {
  ph?: {
    target?: number | null
    min: number
    max: number
  }
  ec?: {
    target?: number | null
    min: number
    max: number
  }
  temp_air?: number
  humidity_air?: number
  light_hours?: number
  irrigation_interval_sec?: number
  irrigation_duration_sec?: number
  irrigation?: Record<string, unknown>
  lighting?: Record<string, unknown>
  climate?: Record<string, unknown>
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

export interface RecipePhaseDayNightExtensions {
  ph?: { day?: number | null; night?: number | null } | null
  ec?: { day?: number | null; night?: number | null } | null
  temperature?: { day?: number | null; night?: number | null } | null
  humidity?: { day?: number | null; night?: number | null } | null
  soil_moisture?: { day?: number | null; night?: number | null } | null
  lighting?: { day_start_time?: string | null; day_hours?: number | null } | null
}

export interface RecipePhaseExtensions {
  day_night?: RecipePhaseDayNightExtensions | null
  subsystems?: {
    irrigation?: {
      targets?: {
        system_type?: string | null
      } | null
      execution?: {
        system_type?: string | null
      } | null
    } | null
  } | null
}

/**
 * Фаза рецепта
 */
export interface RecipePhase {
  id: number
  stage_template_id?: number | null
  stage_template?: {
    id: number
    code?: string | null
    name?: string | null
  } | null
  phase_index: number
  name: string
  duration_hours: number
  duration_days?: number
  phase_started_at?: string | null
  phase_ends_at?: string | null
  targets?: RecipePhaseTargets
  // Flat API fields (alternative to nested targets)
  ph_target?: number | null
  ph_min?: number | null
  ph_max?: number | null
  ec_target?: number | null
  ec_min?: number | null
  ec_max?: number | null
  temp_air_target?: number | null
  humidity_target?: number | null
  lighting_photoperiod_hours?: number | null
  lighting_start_time?: string | null
  irrigation_mode?: string | null
  irrigation_interval_sec?: number | null
  irrigation_duration_sec?: number | null
  irrigation_system_type?: string | null
  substrate_type?: string | null
  nutrient_program_code?: string | null
  nutrient_mode?: 'ratio_ec_pid' | 'delta_ec_by_k' | 'dose_ml_l_only' | null
  nutrient_ec_dosing_mode?: 'sequential' | 'parallel' | null
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
  day_night_enabled?: boolean | null
  extensions?: RecipePhaseExtensions | null
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
  draft_revision_id?: number | null
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
