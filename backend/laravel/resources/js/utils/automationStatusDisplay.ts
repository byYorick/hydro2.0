import type { AutomationState, AutomationStateType } from '@/types/Automation'

const MACRO_PHASE_LABELS: Record<AutomationStateType, string> = {
  IDLE: 'Ожидание',
  TANK_FILLING: 'Наполнение баков',
  TANK_RECIRC: 'Рециркуляция раствора',
  READY: 'Раствор готов',
  IRRIGATING: 'Полив',
  IRRIG_RECIRC: 'Рециркуляция после полива',
}

export function formatAutomationDuration(rawSeconds: number | null | undefined): string {
  if (rawSeconds === null || rawSeconds === undefined) {
    return ''
  }
  const total = Math.floor(Number(rawSeconds))
  if (!Number.isFinite(total) || total <= 0) {
    return ''
  }
  const hours = Math.floor(total / 3600)
  const mm = Math.floor((total % 3600) / 60)
  const ss = total % 60
  if (hours > 0) {
    return `${hours}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
  }
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

export function formatAutomationRemainingLabel(rawSeconds: number | null | undefined): string {
  const duration = formatAutomationDuration(rawSeconds)
  return duration ? `осталось ${duration}` : ''
}

export function formatAutomationDurationLabel(
  rawSeconds: number | null | undefined,
  basis: string | null | undefined,
): string {
  const duration = formatAutomationDuration(rawSeconds)
  if (!duration) {
    return ''
  }
  if (basis === 'terminal_completed') {
    return `Длительность ${duration}`
  }
  return `Прошло ${duration}`
}

/** @deprecated use formatAutomationDurationLabel */
export function formatAutomationElapsedLabel(rawSeconds: number | null | undefined): string {
  return formatAutomationDurationLabel(rawSeconds, null)
}

export function resolveStageHeadline(
  state: AutomationState | null,
  fallbackLabel: string,
): string {
  if (!state) {
    return fallbackLabel
  }

  const details = state.state_details
  if (details?.failed) {
    const human = details.human_error_message?.trim()
    if (human) {
      return human
    }
    const raw = details.error_message?.trim()
    if (raw) {
      return raw
    }
  }

  const stageLabel = state.current_stage_label?.trim()
  if (stageLabel) {
    return stageLabel
  }

  const macroLabel = state.state_label?.trim()
  if (macroLabel) {
    return macroLabel
  }

  return fallbackLabel
}

export function resolveMacroPhaseLabel(
  state: AutomationState | null,
  stateCode: AutomationStateType,
): string {
  if (state?.state_label?.trim()) {
    return state.state_label.trim()
  }
  return MACRO_PHASE_LABELS[stateCode]
}

export function shouldShowProgressPercent(
  progressPercent: number,
  isProcessActive: boolean,
): boolean {
  return progressPercent > 0 || isProcessActive
}

export function buildProgressSummary(params: {
  progressPercent: number
  elapsedSec: number
  estimatedCompletionSec: number | null | undefined
  isProcessActive: boolean
}): string {
  const { progressPercent, elapsedSec, estimatedCompletionSec, isProcessActive } = params
  const elapsed = formatAutomationDuration(elapsedSec)
  const roundedProgress = Math.round(progressPercent)
  const parts: string[] = []

  if (roundedProgress > 0) {
    parts.push(`${roundedProgress}%`)
  }
  if (elapsed) {
    parts.push(elapsed)
  }
  const eta = Number(estimatedCompletionSec ?? 0)
  if (eta > 0) {
    const etaLabel = formatAutomationRemainingLabel(eta)
    if (etaLabel) {
      parts.push(etaLabel)
    }
  }

  if (parts.length > 0) {
    return parts.join(' · ')
  }

  if (isProcessActive) {
    return elapsed ? `Выполняется · ${elapsed}` : 'Выполняется…'
  }

  return '—'
}

export function computeDisplayElapsedSec(params: {
  elapsedSec: number
  stageEnteredAt: string | null | undefined
  servedAt: string | null | undefined
  nowMs: number
}): number {
  const { elapsedSec, stageEnteredAt, servedAt, nowMs } = params

  if (stageEnteredAt) {
    const enteredMs = Date.parse(stageEnteredAt)
    if (Number.isFinite(enteredMs)) {
      return Math.max(0, Math.floor((nowMs - enteredMs) / 1000))
    }
  }

  if (elapsedSec > 0 && servedAt) {
    const servedMs = Date.parse(servedAt)
    if (Number.isFinite(servedMs)) {
      return elapsedSec + Math.max(0, Math.floor((nowMs - servedMs) / 1000))
    }
  }

  return Math.max(0, elapsedSec)
}
