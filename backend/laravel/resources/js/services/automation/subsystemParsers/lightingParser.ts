/**
 * Парсер подсистемы lighting из recipe automation targets.
 *
 * Извлечён из applyAutomationFromRecipe (zoneAutomationTargetsParser.ts).
 * Читает `targets.extensions.subsystems.lighting` + плоский `targets.lighting`
 * fallback и заполняет lightingForm: enabled, interval, lux day/night,
 * photoperiod, schedule (start/end).
 */

import { clamp } from '@/services/automation/parsingUtils'
import {
  asArray,
  asRecord,
  readBoolean,
  readNumber,
  toTimeHHmm,
  type Dictionary,
} from '@/services/automation/dictReaders'
import type { LightingFormState } from '@/composables/zoneAutomationTypes'

export function applyLightingFromTargets(targets: Dictionary, lightingForm: LightingFormState): void {
  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const lightingSubsystem = asRecord(subsystems?.lighting)
  const lightingExecution = asRecord(lightingSubsystem?.execution)
  const lightingTargets = asRecord(lightingSubsystem?.targets)
  const lightingBehavior = lightingExecution ?? lightingTargets
  const lighting = asRecord(targets.lighting)

  const lightingEnabled = readBoolean(lightingSubsystem?.enabled)
  if (lightingEnabled !== null) {
    lightingForm.enabled = lightingEnabled
  }

  const lightingIntervalSec = readNumber(
    lightingBehavior?.interval_sec,
    lightingTargets?.interval_sec,
    lighting?.interval_sec,
  )
  if (lightingIntervalSec !== null) {
    lightingForm.intervalMinutes = clamp(Math.round(lightingIntervalSec / 60), 1, 1440)
  }

  const lux = asRecord(lightingBehavior?.lux) ?? asRecord(lightingTargets?.lux)
  const luxDay = readNumber(lux?.day)
  const luxNight = readNumber(lux?.night)
  if (luxDay !== null) {
    lightingForm.luxDay = clamp(Math.round(luxDay), 0, 120000)
  }
  if (luxNight !== null) {
    lightingForm.luxNight = clamp(Math.round(luxNight), 0, 120000)
  }

  const photoperiod = asRecord(lightingBehavior?.photoperiod) ?? asRecord(lightingTargets?.photoperiod)
  const hoursOn = readNumber(photoperiod?.hours_on, lighting?.photoperiod_hours, targets.light_hours)
  if (hoursOn !== null) {
    lightingForm.hoursOn = clamp(hoursOn, 0, 24)
  }

  const lightingSchedule = asArray(lightingBehavior?.schedule) ?? asArray(lightingTargets?.schedule)
  const firstLightingWindow = asRecord(lightingSchedule?.[0])
  const scheduleStart = toTimeHHmm(firstLightingWindow?.start ?? lighting?.start_time)
  const scheduleEnd = toTimeHHmm(firstLightingWindow?.end)
  if (scheduleStart) {
    lightingForm.scheduleStart = scheduleStart
  }
  if (scheduleEnd) {
    lightingForm.scheduleEnd = scheduleEnd
  }
}
