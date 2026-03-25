export interface RecipePhasePidTargets {
  ph: number | null
  ec: number | null
  phaseLabel: string | null
}

function toFiniteNumber(value: unknown): number | null {
  const normalized = Number(value)
  return Number.isFinite(normalized) ? normalized : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function resolveRecipePhasePidTargets(phase: unknown): RecipePhasePidTargets | null {
  const record = asRecord(phase)
  if (!record) {
    return null
  }

  return {
    ph: toFiniteNumber(record.ph_target),
    ec: toFiniteNumber(record.ec_target),
    phaseLabel: typeof record.name === 'string' && record.name.trim() !== '' ? record.name.trim() : null,
  }
}
