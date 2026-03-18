import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

export function normalizeIrrigationSystem(value: unknown): IrrigationSystem | null {
  const raw = String(value ?? '').trim().toLowerCase()

  if (raw === 'drip') {
    return 'drip'
  }

  if (raw === 'substrate' || raw === 'substrate_trays') {
    return 'substrate_trays'
  }

  if (raw === 'recirc' || raw === 'nft') {
    return 'nft'
  }

  return null
}

export function resolveRecipePhaseSystemType(
  phase: { irrigation_mode?: unknown; extensions?: unknown } | null | undefined,
  fallback: IrrigationSystem
): IrrigationSystem {
  const extensions = asRecord(phase?.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const irrigationSubsystem = asRecord(subsystems?.irrigation)
  const irrigationExecution = asRecord(irrigationSubsystem?.execution)
  const irrigationTargets = asRecord(irrigationSubsystem?.targets)

  const explicitSystemType = normalizeIrrigationSystem(
    irrigationExecution?.system_type ?? irrigationTargets?.system_type
  )
  if (explicitSystemType) {
    return explicitSystemType
  }

  const rawMode = String(phase?.irrigation_mode ?? '').trim().toLowerCase()
  if (rawMode === 'recirc') {
    return 'nft'
  }

  if (rawMode === 'drip') {
    return 'drip'
  }

  if (rawMode === 'substrate') {
    return fallback === 'nft' ? 'drip' : fallback
  }

  return fallback
}

export function resolveSystemTypeFromGrowingSystem(option: {
  id?: string | null
  label?: string | null
  uses_substrate?: boolean
} | null | undefined): IrrigationSystem | null {
  const byId = normalizeIrrigationSystem(option?.id)
  if (byId) {
    return byId
  }

  const label = String(option?.label ?? '').trim().toLowerCase()
  if (label.includes('капел')) {
    return 'drip'
  }

  if (label.includes('nft') || label.includes('рецирк')) {
    return 'nft'
  }

  if (label.includes('лотк') || label.includes('substrate')) {
    return 'substrate_trays'
  }

  if (option?.uses_substrate === true) {
    return 'drip'
  }

  return null
}
