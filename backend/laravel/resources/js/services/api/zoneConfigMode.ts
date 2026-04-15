/**
 * Zone config mode API client (Phase 5/6).
 *
 * Endpoints:
 *   GET    /api/zones/{zone}/config-mode
 *   PATCH  /api/zones/{zone}/config-mode             { mode, reason, live_until? }
 *   PATCH  /api/zones/{zone}/config-mode/extend     { live_until }
 *   GET    /api/zones/{zone}/config-changes?namespace=...
 *   PUT    /api/grow-cycles/{growCycle}/phase-config { reason, <field>: <value>... }
 *   PUT    /api/zones/{zone}/correction/live-edit    { reason, phase?, correction_patch?, calibration_patch? }
 */
import { apiGet, apiPatch, apiPut } from './_client'

export type ConfigMode = 'locked' | 'live'

export interface ConfigModeState {
  zone_id: number
  config_mode: ConfigMode
  config_revision: number
  live_until: string | null
  live_started_at: string | null
  config_mode_changed_at: string | null
  config_mode_changed_by: number | null
}

export interface ConfigModeUpdatePayload {
  mode: ConfigMode
  reason: string
  live_until?: string | null
}

export interface ConfigModeExtendPayload {
  live_until: string
}

export interface ConfigChangeEntry {
  id: number
  revision: number
  namespace: string
  diff: Record<string, unknown>
  user_id: number | null
  reason: string | null
  created_at: string | null
}

export interface ConfigChangesResponse {
  zone_id: number
  changes: ConfigChangeEntry[]
}

export interface PhaseConfigUpdatePayload {
  reason: string
  ph_target?: number | null
  ph_min?: number | null
  ph_max?: number | null
  ec_target?: number | null
  ec_min?: number | null
  ec_max?: number | null
  temp_air_target?: number | null
  humidity_target?: number | null
  co2_target?: number | null
  irrigation_interval_sec?: number | null
  irrigation_duration_sec?: number | null
  lighting_photoperiod_hours?: number | null
  lighting_start_time?: string | null
  mist_interval_sec?: number | null
  mist_duration_sec?: number | null
}

export interface PhaseConfigUpdateResponse {
  status: 'ok'
  grow_cycle_id: number
  phase_id: number
  zone_id: number
  config_revision: number
  updated_fields: string[]
}

export type CorrectionLiveEditPhase =
  | 'generic'
  | 'solution_fill'
  | 'tank_recirc'
  | 'irrigation'

export interface CorrectionLiveEditPayload {
  reason: string
  phase?: CorrectionLiveEditPhase | null
  correction_patch?: Record<string, unknown>
  calibration_patch?: Record<string, unknown>
}

export interface CorrectionLiveEditResponse {
  status: 'ok'
  zone_id: number
  config_revision: number
  phase: CorrectionLiveEditPhase | null
  affected_fields: {
    correction: string[]
    calibration: string[]
  }
}

export const zoneConfigModeApi = {
  show(zoneId: number) {
    return apiGet<ConfigModeState>(`/zones/${zoneId}/config-mode`)
  },

  update(zoneId: number, payload: ConfigModeUpdatePayload) {
    return apiPatch<ConfigModeState>(`/zones/${zoneId}/config-mode`, payload)
  },

  extend(zoneId: number, payload: ConfigModeExtendPayload) {
    return apiPatch<{ zone_id: number; live_until: string }>(
      `/zones/${zoneId}/config-mode/extend`,
      payload,
    )
  },

  changes(zoneId: number, namespace?: string, limit = 50) {
    const qs = new URLSearchParams()
    if (namespace) qs.set('namespace', namespace)
    qs.set('limit', String(limit))
    return apiGet<ConfigChangesResponse>(
      `/zones/${zoneId}/config-changes?${qs.toString()}`,
    )
  },

  updatePhaseConfig(growCycleId: number, payload: PhaseConfigUpdatePayload) {
    return apiPut<PhaseConfigUpdateResponse>(
      `/grow-cycles/${growCycleId}/phase-config`,
      payload,
    )
  },

  updateCorrectionLiveEdit(zoneId: number, payload: CorrectionLiveEditPayload) {
    return apiPut<CorrectionLiveEditResponse>(
      `/zones/${zoneId}/correction/live-edit`,
      payload,
    )
  },
}
