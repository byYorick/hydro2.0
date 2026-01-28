type AnyRecord = Record<string, any>

export function normalizeGrowCycle<T extends AnyRecord | null | undefined>(cycle: T): T {
  if (!cycle || typeof cycle !== 'object') {
    return cycle
  }

  const normalized = { ...cycle } as AnyRecord

  if (!normalized.currentPhase && normalized.current_phase) {
    normalized.currentPhase = normalized.current_phase
  }

  if (!normalized.recipeRevision && normalized.recipe_revision) {
    normalized.recipeRevision = normalized.recipe_revision
  }

  if (!normalized.phases && normalized.phase_snapshots) {
    normalized.phases = normalized.phase_snapshots
  }

  return normalized as T
}
