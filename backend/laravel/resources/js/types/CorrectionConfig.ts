export type CorrectionPhase = 'solution_fill' | 'tank_recirc' | 'irrigation'

export interface CorrectionCatalogField {
  path: string
  label: string
  description: string
  type: 'number' | 'integer' | 'boolean' | 'enum' | 'string'
  min?: number
  max?: number
  step?: number
  unit?: string
  options?: string[]
  readonly?: boolean
  advanced_only?: boolean
}

export interface CorrectionCatalogSection {
  key: string
  label: string
  description: string
  advanced_only?: boolean
  fields: CorrectionCatalogField[]
}

export interface CorrectionPreset {
  id: number
  slug: string
  name: string
  scope: 'system' | 'custom'
  is_locked: boolean
  is_active: boolean
  description: string | null
  config: Record<string, unknown>
  created_by?: number | null
  updated_by?: number | null
  updated_at?: string | null
}

export interface CorrectionRetryConfig {
  max_ec_correction_attempts: number
  max_ph_correction_attempts: number
  prepare_recirculation_timeout_sec: number
  prepare_recirculation_max_attempts: number
  prepare_recirculation_max_correction_attempts: number
  telemetry_stale_retry_sec: number
  decision_window_retry_sec: number
  low_water_retry_sec: number
}

export interface ZoneCorrectionConfigPayload {
  id: number
  zone_id: number
  preset: CorrectionPreset | null
  base_config: Record<string, unknown>
  phase_overrides: Partial<Record<CorrectionPhase, Record<string, unknown>>>
  resolved_config: {
    base: Record<string, unknown>
    phases: Partial<Record<CorrectionPhase, Record<string, unknown>>>
    meta?: Record<string, unknown>
  }
  version: number
  updated_at?: string | null
  updated_by?: number | null
  last_applied_at?: string | null
  last_applied_version?: number | null
  meta: {
    phases: CorrectionPhase[]
    defaults: Record<string, unknown>
    field_catalog: CorrectionCatalogSection[]
  }
  available_presets: CorrectionPreset[]
}

export interface ZoneCorrectionConfigHistoryItem {
  id: number
  version: number
  change_type: string
  preset: CorrectionPreset | null
  changed_by?: number | null
  changed_by_name?: string | null
  changed_at?: string | null
  base_config: Record<string, unknown>
  phase_overrides: Partial<Record<CorrectionPhase, Record<string, unknown>>>
  resolved_config: {
    base: Record<string, unknown>
    phases: Partial<Record<CorrectionPhase, Record<string, unknown>>>
    meta?: Record<string, unknown>
  }
}
