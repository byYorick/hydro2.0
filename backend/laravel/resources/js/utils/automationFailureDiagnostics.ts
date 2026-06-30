import type { AutomationObservability, AutomationState } from '@/types/Automation'
import { stageDiagnosticLabel } from '@/utils/automationObservability'
import {
  automationIndicatesActiveFailure,
  automationIndicatesHistoricalFailure,
} from '@/utils/automationFailureState'
import { resolveErrorCatalogEntry, resolveHumanErrorMessage } from '@/utils/errorCatalog'

export interface AutomationFailureDiagnostics {
  isActiveFailure: boolean
  isHistoricalFailure: boolean
  title: string
  summary: string | null
  errorCode: string | null
  technicalMessage: string | null
  failedStage: string | null
  failedStageLabel: string | null
  taskId: number | null
  failedAt: string | null
  workflowPhase: string | null
}

function pickString(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim() !== '') {
      return value.trim()
    }
  }
  return null
}

function pickTaskId(...values: Array<number | string | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
      return value
    }
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed) && parsed > 0) {
        return parsed
      }
    }
  }
  return null
}

export function resolveAutomationFailureDiagnostics(
  state: AutomationState | null,
  observability?: AutomationObservability | null,
): AutomationFailureDiagnostics | null {
  if (!state) {
    return null
  }

  const resolvedObservability = observability ?? state.observability ?? null
  const runtime = resolvedObservability?.runtime
  const runtimeFailed = runtime?.task_status === 'failed' && runtime?.task_is_active === false
  const isActiveFailure = automationIndicatesActiveFailure(state)
  const isHistoricalFailure = !isActiveFailure && (
    runtimeFailed || automationIndicatesHistoricalFailure(state)
  )

  if (!isActiveFailure && !isHistoricalFailure) {
    return null
  }

  const details = state.state_details
  const lastFailure = state.last_terminal_failure
  const errorCode = pickString(
    details?.error_code,
    lastFailure?.error_code,
  )
  const catalog = resolveErrorCatalogEntry(errorCode)
  const technicalMessage = pickString(
    details?.error_message,
    lastFailure?.error_message,
  )
  const summary = resolveHumanErrorMessage({
    code: errorCode,
    message: technicalMessage,
    humanMessage: pickString(
      details?.human_error_message,
      lastFailure?.human_error_message,
      catalog.message,
    ),
  })

  const failedStage = pickString(
    runtime?.failed_stage,
    state.current_stage,
  )
  const taskId = pickTaskId(
    runtime?.task_id,
    details?.failed_task_id,
    lastFailure?.task_id,
  )

  const title = isHistoricalFailure && !isActiveFailure
    ? 'Последний сбой автоматики'
    : (catalog.title ?? 'Сбой задачи автоматики')

  return {
    isActiveFailure,
    isHistoricalFailure: isHistoricalFailure && !isActiveFailure,
    title,
    summary,
    errorCode,
    technicalMessage: technicalMessage && technicalMessage !== summary ? technicalMessage : null,
    failedStage,
    failedStageLabel: failedStage ? stageDiagnosticLabel(failedStage) : null,
    taskId,
    failedAt: pickString(lastFailure?.failed_at ?? null),
    workflowPhase: pickString(
      runtime?.workflow_phase,
      state.workflow_phase,
    ),
  }
}
