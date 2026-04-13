/**
 * Унифицированная синхронизация форм автоматики зоны из фазы рецепта.
 *
 * Используется Setup Wizard и Growth Cycle Wizard для первичной подстановки
 * целей (pH, EC, климат, освещение, полив) из выбранного рецепта/фазы.
 *
 * Специфика каждого мастера задаётся через опции — общая логика парсинга
 * и записи значений живёт здесь.
 */

import { addHoursToTime } from '@/composables/growthCycleWizardHelpers'
import { resolveRecipePhaseSystemType } from '@/composables/recipeSystemType'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'
import { clamp, isValidHHMM, toFiniteNumber } from './parsingUtils'

export interface RecipePhaseLike {
  ph_target?: number | null
  ec_target?: number | null
  temp_air_target?: number | null
  humidity_target?: number | null
  lighting_photoperiod_hours?: number | null
  lighting_start_time?: string | null
  irrigation_interval_sec?: number | null
  irrigation_duration_sec?: number | null
  extensions?: Record<string, unknown> | null
}

export interface PhaseSyncTargets {
  waterForm: WaterFormState
  climateForm: ClimateFormState
  lightingForm: LightingFormState
}

export interface PhaseSyncOptions {
  /**
   * Читать day/night climate из `phase.extensions.day_night.*` с fallback
   * на плоские `temp_air_target`/`humidity_target`. Используется Setup.
   */
  readDayNightExtensions?: boolean
  /** Минимум irrigationIntervalMinutes (Setup=1, Growth=5). */
  minIntervalMinutes?: number
  /** Минимум durationSeconds (Setup=1, Growth=10). */
  minDurationSeconds?: number
  /** Подставлять luxDay из photoperiod (Setup). */
  syncLuxDayFromPhotoperiod?: boolean
  /** Подставлять scheduleStart/scheduleEnd для освещения (Growth). */
  syncLightingSchedule?: boolean
  /** Включать климат по факту синхронизации (Growth). */
  enableClimateOnSync?: boolean
}

function readDayTemperature(phase: RecipePhaseLike): number | null {
  const ext = phase.extensions as
    | { day_night?: { temperature?: { day?: unknown } } }
    | null
    | undefined
  return toFiniteNumber(ext?.day_night?.temperature?.day ?? phase.temp_air_target)
}

function readDayHumidity(phase: RecipePhaseLike): number | null {
  const ext = phase.extensions as
    | { day_night?: { humidity?: { day?: unknown } } }
    | null
    | undefined
  return toFiniteNumber(ext?.day_night?.humidity?.day ?? phase.humidity_target)
}

export function syncFormsFromRecipePhase(
  phase: RecipePhaseLike,
  forms: PhaseSyncTargets,
  opts: PhaseSyncOptions = {},
): void {
  const { waterForm, climateForm, lightingForm } = forms
  const minInterval = opts.minIntervalMinutes ?? 1
  const minDuration = opts.minDurationSeconds ?? 1

  // systemType — меняется через waterForm, канонический watcher
  // syncSystemToTankLayout скорректирует tanksCount.
  waterForm.systemType = resolveRecipePhaseSystemType(phase, waterForm.systemType)

  const phTarget = toFiniteNumber(phase.ph_target)
  const ecTarget = toFiniteNumber(phase.ec_target)
  const tempAirTarget = opts.readDayNightExtensions
    ? readDayTemperature(phase)
    : toFiniteNumber(phase.temp_air_target)
  const humidityTarget = opts.readDayNightExtensions
    ? readDayHumidity(phase)
    : toFiniteNumber(phase.humidity_target)
  const photoperiod = toFiniteNumber(phase.lighting_photoperiod_hours)
  const intervalSec = toFiniteNumber(phase.irrigation_interval_sec)
  const durationSec = toFiniteNumber(phase.irrigation_duration_sec)

  if (phTarget !== null) {
    waterForm.targetPh = Number(phTarget.toFixed(2))
  }
  if (ecTarget !== null) {
    waterForm.targetEc = Number(ecTarget.toFixed(2))
  }
  if (tempAirTarget !== null) {
    climateForm.dayTemp = Number(tempAirTarget.toFixed(1))
  }
  if (humidityTarget !== null) {
    climateForm.dayHumidity = Math.round(humidityTarget)
  }

  if (photoperiod !== null) {
    lightingForm.hoursOn = clamp(Math.round(photoperiod), 1, 24)

    if (opts.syncLuxDayFromPhotoperiod) {
      lightingForm.luxDay = Math.max(4000, photoperiod * 1000)
    }

    if (opts.syncLightingSchedule) {
      const raw = String(phase.lighting_start_time || '')
      const scheduleStart = isValidHHMM(raw) ? raw : '06:00'
      lightingForm.scheduleStart = scheduleStart
      lightingForm.scheduleEnd = addHoursToTime(scheduleStart, lightingForm.hoursOn)
    }
  }

  if (intervalSec !== null && intervalSec > 0) {
    waterForm.intervalMinutes = Math.max(minInterval, Math.round(intervalSec / 60))
  }
  if (durationSec !== null && durationSec > 0) {
    waterForm.durationSeconds = Math.max(minDuration, Math.round(durationSec))
  }

  if (opts.enableClimateOnSync) {
    climateForm.enabled = true
  }
}
