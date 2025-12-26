/**
 * Статус цикла выращивания
 */
export type GrowCycleStatus = 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'ABORTED' | 'HARVESTED'

/**
 * Модель цикла выращивания
 */
export interface GrowCycle {
  id: number
  zone_id: number
  recipe_id: number
  recipe?: {
    id: number
    name: string
    phases?: Array<{
      id: number
      name: string
      duration_hours: number
      targets?: Record<string, any>
    }>
  }
  status: GrowCycleStatus
  started_at: string | null
  paused_at: string | null
  completed_at: string | null
  aborted_at: string | null
  harvested_at: string | null
  expected_harvest_at: string | null
  current_stage_code?: string
  current_phase_index?: number | null
  current_phase_name?: string | null
  batch_label?: string | null
  planting_at?: string | null
  created_at: string
  updated_at: string
}


