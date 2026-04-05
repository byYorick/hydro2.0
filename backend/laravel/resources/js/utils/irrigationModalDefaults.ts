/**
 * Длительность полива из целей фазы рецепта (плоская или nested irrigation).
 */
export function pickIrrigationDurationFromTargets(targets: unknown): number | undefined {
  if (!targets || typeof targets !== 'object') return undefined
  const t = targets as Record<string, unknown>
  const top = Number(t.irrigation_duration_sec)
  if (Number.isFinite(top) && top >= 1) return Math.min(3600, Math.round(top))
  const topSec = Number(t.irrigation_duration_seconds)
  if (Number.isFinite(topSec) && topSec >= 1) return Math.min(3600, Math.round(topSec))
  const irr = t.irrigation
  if (irr && typeof irr === 'object' && !Array.isArray(irr)) {
    const i = irr as Record<string, unknown>
    for (const key of ['duration_sec', 'duration_seconds', 'irrigation_duration_sec'] as const) {
      const d = Number(i[key])
      if (Number.isFinite(d) && d >= 1) return Math.min(3600, Math.round(d))
    }
  }
  return undefined
}
