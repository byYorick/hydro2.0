/**
 * Парсер подсистемы solution_change из recipe automation targets.
 *
 * Извлечён из applyAutomationFromRecipe (zoneAutomationTargetsParser.ts).
 * Читает `targets.extensions.subsystems.solution_change` (или alias `solution`)
 * + плоский `targets.solution_change` fallback и заполняет соответствующие
 * поля waterForm: solutionChangeEnabled, solutionChangeIntervalMinutes,
 * solutionChangeDurationSeconds.
 */

import { clamp } from '@/services/automation/parsingUtils'
import {
  asRecord,
  readBoolean,
  readNumber,
  type Dictionary,
} from '@/services/automation/dictReaders'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

export function applySolutionChangeFromTargets(targets: Dictionary, waterForm: WaterFormState): void {
  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const solutionSubsystem = asRecord(subsystems?.solution_change ?? subsystems?.solution)
  const solutionExecution = asRecord(solutionSubsystem?.execution)
  const solutionTargets = asRecord(solutionSubsystem?.targets)
  const solutionBehavior = solutionExecution ?? solutionTargets
  const solutionChange = asRecord(targets.solution_change)

  const solutionEnabled = readBoolean(solutionSubsystem?.enabled)
  if (solutionEnabled !== null) {
    waterForm.solutionChangeEnabled = solutionEnabled
  }

  const solutionIntervalSec = readNumber(
    solutionBehavior?.interval_sec,
    solutionTargets?.interval_sec,
    solutionChange?.interval_sec,
  )
  if (solutionIntervalSec !== null) {
    waterForm.solutionChangeIntervalMinutes = clamp(Math.round(solutionIntervalSec / 60), 1, 1440)
  }

  const solutionDurationSec = readNumber(
    solutionBehavior?.duration_sec,
    solutionTargets?.duration_sec,
    solutionChange?.duration_sec,
  )
  if (solutionDurationSec !== null) {
    waterForm.solutionChangeDurationSeconds = clamp(Math.round(solutionDurationSec), 1, 86400)
  }
}
