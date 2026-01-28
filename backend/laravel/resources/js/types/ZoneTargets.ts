/**
 * Целевые значения для зоны
 */
export interface ZoneTargets extends Record<string, number | undefined> {
  ph_min: number
  ph_max: number
  ec_min: number
  ec_max: number
  temp_min: number
  temp_max: number
  humidity_min: number
  humidity_max: number
  irrigation_interval_sec?: number
  light_hours?: number
}

