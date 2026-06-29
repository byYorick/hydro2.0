import type { AutomationState } from '@/types/Automation'

export function automationIndicatesActiveFailure(state: AutomationState | null): boolean {
  return Boolean(state?.state_details?.failed)
}

export function automationIndicatesHistoricalFailure(state: AutomationState | null): boolean {
  if (automationIndicatesActiveFailure(state)) {
    return false
  }
  const last = state?.last_terminal_failure
  return Boolean(last?.error_code || last?.human_error_message || last?.error_message)
}

export function timelineIndicatesTerminalFailure(state: AutomationState | null): boolean {
  const timeline = state?.timeline ?? []
  const latest = timeline[timeline.length - 1]
  if (!latest) {
    return false
  }
  const eventCode = String(latest.event ?? '').toUpperCase()
  return eventCode === 'SCHEDULE_TASK_FAILED' || eventCode === 'TASK_FAILED'
}

/** Unified terminal failure для workflow bar и alerts. */
export function automationHasTerminalFailure(state: AutomationState | null): boolean {
  return automationIndicatesActiveFailure(state)
    || automationIndicatesHistoricalFailure(state)
    || timelineIndicatesTerminalFailure(state)
}
