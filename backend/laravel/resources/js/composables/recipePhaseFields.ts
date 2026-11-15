/** Field conversions and target edits shared by the recipe phase UI. */
import type { RecipePhaseFormState, EcBreakdown } from './recipeEditorShared'
import { computeEcBreakdown, nullableDraftNumber } from './recipeEditorShared'

// ── Длительность фазы (ДД:ЧЧ) ──
function durationDays(phase: RecipePhaseFormState): number {
  return Math.floor((phase.duration_hours ?? 0) / 24)
}
function durationHoursPart(phase: RecipePhaseFormState): number {
  return (phase.duration_hours ?? 0) % 24
}
export function durationDisplay(phase: RecipePhaseFormState): string {
  const d = durationDays(phase)
  const h = durationHoursPart(phase)
  return `${d} : ${String(h).padStart(2, '0')}`
}
export function setDurationFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const d = Math.max(0, Number(parts[0]) || 0)
  const h = parts.length > 1 ? Math.max(0, Math.min(23, Number(parts[1]) || 0)) : 0
  phase.duration_hours = d * 24 + h
}

// ── Интервал полива (ЧЧ:ММ) ──
export function intervalDisplay(phase: RecipePhaseFormState): string {
  const sec = phase.irrigation_interval_sec ?? 0
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return `${String(h).padStart(2, '0')} : ${String(m).padStart(2, '0')}`
}
export function setIntervalFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const h = Math.max(0, Number(parts[0]) || 0)
  const m = parts.length > 1 ? Math.max(0, Math.min(59, Number(parts[1]) || 0)) : 0
  phase.irrigation_interval_sec = h * 3600 + m * 60
}

// ── Длительность полива (ММ:СС) ──
export function durationIrrigDisplay(phase: RecipePhaseFormState): string {
  const sec = phase.irrigation_duration_sec ?? 0
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')} : ${String(s).padStart(2, '0')}`
}
export function setDurationIrrigFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const m = Math.max(0, Number(parts[0]) || 0)
  const s = parts.length > 1 ? Math.max(0, Math.min(59, Number(parts[1]) || 0)) : 0
  phase.irrigation_duration_sec = m * 60 + s
}

export type CropDayNumberKey =
  | 'solution_temp_min'
  | 'solution_temp_max'
  | 'solution_health_breach_hold_sec'
  | 'dli_target'
  | 'solution_max_age_days'
  | 'solution_refresh_after_topup_ml'

export function cropDayInputValue(value: number | null): string | number {
  return value === null || value === undefined ? '' : value
}

export function setCropDayNumber(phase: RecipePhaseFormState, key: CropDayNumberKey, event: Event): void {
  phase[key] = nullableDraftNumber((event.target as HTMLInputElement).value)
}

export function onPhTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ph_target ?? 0
  phase.ph_min = +(t - 0.1).toFixed(2)
  phase.ph_max = +(t + 0.1).toFixed(2)
}

export function onEcTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ec_target ?? 0
  phase.ec_min = +(t - 0.1).toFixed(2)
  phase.ec_max = +(t + 0.1).toFixed(2)
}

export function onPhNightTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.day_night.ph.night ?? 0
  phase.day_night.ph.night_min = +(t - 0.1).toFixed(2)
  phase.day_night.ph.night_max = +(t + 0.1).toFixed(2)
}

export function onEcNightTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.day_night.ec.night ?? 0
  phase.day_night.ec.night_min = +(t - 0.1).toFixed(2)
  phase.day_night.ec.night_max = +(t + 0.1).toFixed(2)
}

export function ecBreakdown(phase: RecipePhaseFormState): EcBreakdown {
  return computeEcBreakdown(phase)
}

// Пересчитать EC breakdown для произвольного target (day / night)
export function ecBreakdownForTarget(phase: RecipePhaseFormState, _ph: number, ecTarget: number): EcBreakdown {
  return computeEcBreakdown({ ...phase, ec_target: ecTarget || 0 })
}

// Проверка: показывать ли breakdown при включенном day_night
export function ecBreakdownsDayNight(phase: RecipePhaseFormState): boolean {
  const b = ecBreakdown(phase)
  return b.total > 0 && b.npkShare > 0 && b.npkShare < 1
}
