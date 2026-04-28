import type { AutomationDocument } from '@/composables/useAutomationConfig'

export type ZoneAutomationLogicMode = 'setup' | 'working'

export interface ZoneAutomationLogicProfileEntry {
  mode: ZoneAutomationLogicMode
  is_active: boolean
  subsystems: Record<string, unknown>
  command_plans?: Record<string, unknown>
  updated_at: string | null
  updated_by?: number | null
  created_at?: string | null
  created_by?: number | null
}

export interface ZoneAutomationLogicProfilePayload {
  active_mode: ZoneAutomationLogicMode | null
  profiles: Partial<Record<ZoneAutomationLogicMode, ZoneAutomationLogicProfileEntry>>
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function asMode(value: unknown): ZoneAutomationLogicMode | null {
  return value === 'setup' || value === 'working' ? value : null
}

function normalizeEntry(value: unknown, fallbackMode?: ZoneAutomationLogicMode): ZoneAutomationLogicProfileEntry | null {
  const record = asRecord(value)
  if (!record) {
    return null
  }

  const mode = asMode(record.mode) ?? fallbackMode ?? null
  const subsystems = asRecord(record.subsystems)
  if (!mode || !subsystems) {
    return null
  }

  const commandPlans = asRecord(record.command_plans)

  return {
    mode,
    is_active: record.is_active === true,
    subsystems,
    command_plans: commandPlans ?? undefined,
    updated_at: typeof record.updated_at === 'string' ? record.updated_at : null,
    updated_by: typeof record.updated_by === 'number' ? record.updated_by : null,
    created_at: typeof record.created_at === 'string' ? record.created_at : null,
    created_by: typeof record.created_by === 'number' ? record.created_by : null,
  }
}

export function normalizeZoneLogicProfilePayload(raw: unknown): ZoneAutomationLogicProfilePayload {
  const record = asRecord(raw)
  const rawProfiles = asRecord(record?.profiles)
  const profiles: Partial<Record<ZoneAutomationLogicMode, ZoneAutomationLogicProfileEntry>> = {}

  for (const mode of ['setup', 'working'] as const) {
    const entry = normalizeEntry(rawProfiles?.[mode], mode)
    if (entry) {
      profiles[mode] = entry
    }
  }

  return {
    active_mode: asMode(record?.active_mode) ?? null,
    profiles,
  }
}

export function payloadFromZoneLogicDocument(
  document: AutomationDocument<Record<string, unknown>>,
): ZoneAutomationLogicProfilePayload {
  return normalizeZoneLogicProfilePayload(document.payload ?? {})
}

export function resolveZoneLogicProfileEntry(
  payload: ZoneAutomationLogicProfilePayload,
  preferredMode?: ZoneAutomationLogicMode | null,
): ZoneAutomationLogicProfileEntry | null {
  const candidates = [
    preferredMode,
    payload.active_mode,
    'working' as const,
    'setup' as const,
  ]

  for (const mode of candidates) {
    if (!mode) {
      continue
    }

    const entry = payload.profiles[mode]
    if (entry?.subsystems) {
      return entry
    }
  }

  return null
}

export function extractZoneLogicSubsystems(
  document: AutomationDocument<Record<string, unknown>>,
  preferredMode?: ZoneAutomationLogicMode | null,
): Record<string, unknown> | null {
  const payload = payloadFromZoneLogicDocument(document)
  return resolveZoneLogicProfileEntry(payload, preferredMode)?.subsystems ?? null
}

export function upsertZoneLogicProfilePayload(
  current: ZoneAutomationLogicProfilePayload,
  mode: ZoneAutomationLogicMode,
  subsystems: Record<string, unknown>,
  activate = true,
): ZoneAutomationLogicProfilePayload {
  const nextProfiles: Partial<Record<ZoneAutomationLogicMode, ZoneAutomationLogicProfileEntry>> = {
    ...current.profiles,
  }
  const now = new Date().toISOString()
  const previousEntry = current.profiles[mode]

  nextProfiles[mode] = {
    mode,
    is_active: activate || previousEntry?.is_active === true,
    subsystems,
    ...(previousEntry?.command_plans ? { command_plans: previousEntry.command_plans } : {}),
    updated_at: now,
    updated_by: previousEntry?.updated_by ?? null,
    created_at: previousEntry?.created_at ?? now,
    created_by: previousEntry?.created_by ?? null,
  }

  if (activate) {
    for (const candidate of ['setup', 'working'] as const) {
      const entry = nextProfiles[candidate]
      if (!entry) {
        continue
      }

      nextProfiles[candidate] = {
        ...entry,
        is_active: candidate === mode,
      }
    }
  }

  return {
    active_mode: activate ? mode : (current.active_mode ?? mode),
    profiles: nextProfiles,
  }
}
