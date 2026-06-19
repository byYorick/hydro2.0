/**
 * Shared utility functions for zone automation composables.
 * Keep this file free of Vue reactivity imports.
 */

import type { AutomationControlMode, AutomationManualStep } from '@/types/Automation'

export type AutomationLogicMode = 'setup' | 'working'

// ─── Automation control mode / manual steps ───────────────────────────────────

export const AUTOMATION_MANUAL_STEPS_SET = new Set<AutomationManualStep>([
  'clean_fill_start',
  'clean_fill_stop',
  'solution_fill_start',
  'force_solution_fill_start',
  'solution_fill_stop',
  'prepare_recirculation_stop',
  'irrigation_stop',
  'irrigation_recovery_stop',
])

export function normalizeAutomationControlMode(value: unknown): AutomationControlMode {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'semi' || normalized === 'manual') return normalized
  return 'auto'
}

/** true только если API явно передал control_mode (не пустой / не undefined). */
export function hasExplicitControlMode(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false
  }
  const normalized = String(value).trim().toLowerCase()
  return normalized === 'auto' || normalized === 'semi' || normalized === 'manual'
}

const ALL_CONTROL_MODES: AutomationControlMode[] = ['auto', 'semi', 'manual']

export function normalizeAutomationControlModes(value: unknown): AutomationControlMode[] {
  if (!Array.isArray(value) || value.length === 0) return ALL_CONTROL_MODES
  const filtered = value
    .map((item) => String(item ?? '').trim().toLowerCase())
    .filter((item): item is AutomationControlMode => item === 'auto' || item === 'semi' || item === 'manual')
  return filtered.length > 0 ? filtered : ALL_CONTROL_MODES
}

export function normalizeAutomationManualSteps(value: unknown): AutomationManualStep[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => String(item ?? '').trim().toLowerCase())
    .filter((item): item is AutomationManualStep => AUTOMATION_MANUAL_STEPS_SET.has(item as AutomationManualStep))
}

/** Зеркало ae3lite/application/use_cases/manual_control_contract.py */
const ALLOWED_MANUAL_STEPS_BY_STAGE: Record<string, AutomationManualStep[]> = {
  startup: ['clean_fill_start', 'solution_fill_start', 'force_solution_fill_start'],
  clean_fill_start: ['clean_fill_stop'],
  clean_fill_check: ['clean_fill_stop'],
  solution_fill_start: ['solution_fill_stop'],
  solution_fill_check: ['solution_fill_stop'],
  prepare_recirculation_start: ['prepare_recirculation_stop'],
  prepare_recirculation_check: ['prepare_recirculation_stop'],
  irrigation_start: ['irrigation_stop'],
  irrigation_check: ['irrigation_stop'],
  irrigation_recovery_check: ['irrigation_recovery_stop'],
}

export function allowedManualStepsForStage(stage: unknown): AutomationManualStep[] {
  const normalizedStage = String(stage ?? '').trim().toLowerCase()
  if (!normalizedStage) return []
  return [...(ALLOWED_MANUAL_STEPS_BY_STAGE[normalizedStage] ?? [])]
}

/** API — source of truth; при пустом списке выводим шаги из current_stage (manual/semi). */
export function resolveAllowedManualSteps(
  controlMode: AutomationControlMode,
  currentStage: string | null | undefined,
  fromApi: AutomationManualStep[] | undefined,
): AutomationManualStep[] {
  if (controlMode === 'auto') return []
  const derived = allowedManualStepsForStage(currentStage)
  if (fromApi && fromApi.length > 0) return fromApi
  return derived
}

export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value === 'string') {
    const normalized = value.trim()
    if (normalized === '') return null

    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

export function normalizeAutomationLogicMode(
  value: unknown,
  fallback: AutomationLogicMode = 'working'
): AutomationLogicMode {
  return value === 'setup' ? 'setup' : value === 'working' ? 'working' : fallback
}

export function normalizeIsoInput(rawValue: string): string {
  const raw = rawValue.trim()
  if (!raw) return raw

  const hasTimezone = /(?:Z|z|[+-]\d{2}:\d{2})$/.test(raw)
  const looksIsoDateTime = /^\d{4}-\d{2}-\d{2}T/.test(raw)
  if (looksIsoDateTime && !hasTimezone) {
    return `${raw}Z`
  }
  return raw
}

export function parseIsoDate(value: string | null | undefined): Date | null {
  const raw = normalizeIsoInput(String(value ?? ''))
  if (!raw) return null
  const parsed = new Date(raw)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatRelativeMs(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes <= 0) return `${seconds}с`
  if (minutes < 60) return `${minutes}м ${seconds}с`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return `${hours}ч ${restMinutes}м`
}
