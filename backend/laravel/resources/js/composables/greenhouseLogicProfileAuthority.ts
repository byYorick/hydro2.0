export const GREENHOUSE_LOGIC_PROFILE_NAMESPACE = 'greenhouse.logic_profile'

export interface GreenhouseClimateBindingsState {
  climate_sensors: number[]
  weather_station_sensors: number[]
  vent_actuators: number[]
  fan_actuators: number[]
}

export interface GreenhouseAutomationLogicProfileEntry {
  mode: string
  is_active: boolean
  subsystems?: Record<string, unknown>
  updated_at?: string | null
}

export interface GreenhouseAutomationLogicProfilesResponse {
  active_mode?: string | null
  profiles?: Record<string, GreenhouseAutomationLogicProfileEntry>
  bindings?: Partial<GreenhouseClimateBindingsState>
  storage_ready?: boolean
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

export function toNodeIdArray(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return []
  }

  return Array.from(new Set(
    value
      .map((item) => Number(item))
      .filter((item) => Number.isInteger(item) && item > 0)
  ))
}

export function payloadFromGreenhouseLogicDocument(document: { payload?: unknown; active_mode?: unknown; profiles?: unknown; bindings?: unknown } | null | undefined): GreenhouseAutomationLogicProfilesResponse | null {
  if (!document || typeof document !== 'object') {
    return null
  }

  const payload = asRecord(document.payload ?? null)
  const root = asRecord(document)

  return {
    active_mode: typeof root?.active_mode === 'string'
      ? root.active_mode
      : (typeof payload?.active_mode === 'string' ? payload.active_mode : null),
    profiles: asRecord(root?.profiles ?? null) ?? asRecord(payload?.profiles ?? null) ?? {},
    bindings: asRecord(root?.bindings ?? null) as Partial<GreenhouseClimateBindingsState> | undefined,
    storage_ready: Boolean(root?.storage_ready ?? true),
  }
}

export function resolveGreenhouseProfileEntry(data: GreenhouseAutomationLogicProfilesResponse | null): GreenhouseAutomationLogicProfileEntry | null {
  const profiles = asRecord(data?.profiles ?? null)
  if (!profiles) {
    return null
  }

  const activeMode = typeof data?.active_mode === 'string' ? data.active_mode : null
  const preferredModes = [activeMode, 'setup', 'working']
    .filter((value): value is string => typeof value === 'string' && value.length > 0)

  for (const mode of preferredModes) {
    const candidate = asRecord(profiles[mode])
    if (!candidate) {
      continue
    }

    return {
      mode: typeof candidate.mode === 'string' ? candidate.mode : mode,
      is_active: typeof candidate.is_active === 'boolean' ? candidate.is_active : mode === activeMode,
      subsystems: asRecord(candidate.subsystems ?? null) ?? undefined,
      updated_at: typeof candidate.updated_at === 'string' ? candidate.updated_at : null,
    }
  }

  return null
}

export function upsertGreenhouseLogicProfilePayload(
  currentPayload: GreenhouseAutomationLogicProfilesResponse | null,
  mode: 'setup' | 'working',
  subsystems: Record<string, unknown>,
  activate = true,
): Record<string, unknown> {
  const profiles = asRecord(currentPayload?.profiles ?? null) ?? {}
  const nextProfiles: Record<string, unknown> = { ...profiles }

  nextProfiles[mode] = {
    mode,
    is_active: activate,
    subsystems,
    updated_at: new Date().toISOString(),
  }

  if (activate) {
    for (const [profileMode, value] of Object.entries(nextProfiles)) {
      if (profileMode === mode) {
        continue
      }

      const profile = asRecord(value)
      if (!profile) {
        continue
      }

      nextProfiles[profileMode] = {
        ...profile,
        is_active: false,
      }
    }
  }

  return {
    active_mode: activate ? mode : (typeof currentPayload?.active_mode === 'string' ? currentPayload.active_mode : null),
    profiles: nextProfiles,
  }
}
