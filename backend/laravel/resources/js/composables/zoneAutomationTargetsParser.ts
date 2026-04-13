/**
 * Главный диспетчер парсинга recipe automation targets.
 *
 * Применяет pH/EC core targets и делегирует конкретные подсистемы в
 * subsystemParsers/ (irrigation, climate, lighting, diagnostics, solution_change).
 *
 * Reader-утилиты вынесены в @/services/automation/dictReaders, утилита
 * `syncSystemToTankLayout` — в @/services/automation/tankLayout.
 */

import { clamp } from '@/services/automation/parsingUtils'
import { asRecord, readNumber } from '@/services/automation/dictReaders'
import { applyClimateFromTargets } from '@/services/automation/subsystemParsers/climateParser'
import { applyDiagnosticsFromTargets } from '@/services/automation/subsystemParsers/diagnosticsParser'
import { applyIrrigationFromTargets } from '@/services/automation/subsystemParsers/irrigationParser'
import { applyLightingFromTargets } from '@/services/automation/subsystemParsers/lightingParser'
import { applySolutionChangeFromTargets } from '@/services/automation/subsystemParsers/solutionChangeParser'
import { syncSystemToTankLayout } from '@/services/automation/tankLayout'
import type { ZoneAutomationForms } from './zoneAutomationTypes'

export { clamp, syncSystemToTankLayout }

export function applyAutomationFromRecipe(targetsInput: unknown, forms: ZoneAutomationForms): void {
  const { climateForm, waterForm, lightingForm } = forms
  const targets = asRecord(targetsInput)
  if (!targets) {
    return
  }

  const phTarget = asRecord(targets.ph)
  const phValue = readNumber(phTarget?.target)
  if (phValue !== null) {
    waterForm.targetPh = clamp(phValue, 4, 9)
  }

  const ecTarget = asRecord(targets.ec)
  const ecValue = readNumber(ecTarget?.target)
  if (ecValue !== null) {
    waterForm.targetEc = clamp(ecValue, 0.1, 10)
  }

  applyIrrigationFromTargets(targets, waterForm)
  applyClimateFromTargets(targets, climateForm)
  applyLightingFromTargets(targets, lightingForm)
  applyDiagnosticsFromTargets(targets, waterForm)
  applySolutionChangeFromTargets(targets, waterForm)
}
