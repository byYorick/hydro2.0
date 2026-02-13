import { clamp, syncSystemToTankLayout } from './zoneAutomationTargetsParser'
import type { ZoneAutomationForms } from './zoneAutomationTypes'

function normalizeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  return fallback
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

export function validateForms(forms: Pick<ZoneAutomationForms, 'climateForm' | 'waterForm'>): string | null {
  const { climateForm, waterForm } = forms
  if (climateForm.ventMinPercent > climateForm.ventMaxPercent) {
    return 'Минимум открытия форточек не может быть больше максимума.'
  }

  if (waterForm.cleanTankFillL <= 0 || waterForm.nutrientTankTargetL <= 0) {
    return 'Укажите положительные объёмы баков.'
  }

  if (waterForm.tanksCount === 3 && waterForm.enableDrainControl && waterForm.drainTargetPercent <= 0) {
    return 'Для контроля дренажа задайте целевой процент больше 0.'
  }

  if (waterForm.cleanTankFullThreshold <= 0 || waterForm.cleanTankFullThreshold > 1) {
    return 'Порог полного бака должен быть в диапазоне (0;1].'
  }

  return null
}

export function buildGrowthCycleConfigPayload(
  forms: ZoneAutomationForms,
  options?: { includeSystemType?: boolean }
): Record<string, unknown> {
  const { climateForm, waterForm, lightingForm } = forms
  const includeSystemType = options?.includeSystemType ?? true
  const phTarget = clamp(normalizeNumber(waterForm.targetPh, 5.8), 4, 9)
  const ecTarget = clamp(normalizeNumber(waterForm.targetEc, 1.6), 0.1, 10)

  const phMin = round(clamp(phTarget - 0.2, 4, 9), 2)
  const phMax = round(clamp(phTarget + 0.2, 4, 9), 2)
  const ecMin = round(clamp(ecTarget - 0.2, 0.1, 10), 2)
  const ecMax = round(clamp(ecTarget + 0.2, 0.1, 10), 2)

  const irrigationIntervalMinutes = clamp(Math.round(waterForm.intervalMinutes), 5, 1440)
  const irrigationDurationSeconds = clamp(Math.round(waterForm.durationSeconds), 1, 3600)
  const climateIntervalSec = clamp(Math.round(climateForm.intervalMinutes * 60), 60, 86400)
  const lightingIntervalSec = clamp(Math.round(lightingForm.intervalMinutes * 60), 60, 86400)
  const diagnosticsIntervalSec = clamp(Math.round(waterForm.diagnosticsIntervalMinutes * 60), 60, 86400)
  const solutionChangeIntervalSec = clamp(Math.round(waterForm.solutionChangeIntervalMinutes * 60), 60, 86400)
  const solutionChangeDurationSec = clamp(Math.round(waterForm.solutionChangeDurationSeconds), 1, 86400)
  const cleanTankFullThreshold = round(clamp(waterForm.cleanTankFullThreshold, 0.05, 1), 3)

  const requiredNodeTypes = waterForm.refillRequiredNodeTypes
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
  const refillPreferredChannel = waterForm.refillPreferredChannel.trim()

  const diagnosticsExecution: Record<string, unknown> = {
    workflow: waterForm.cycleStartWorkflowEnabled ? 'cycle_start' : 'diagnostics',
    clean_tank_full_threshold: cleanTankFullThreshold,
    required_node_types: requiredNodeTypes,
    refill_duration_sec: clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600),
    refill_timeout_sec: clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400),
    refill: {
      duration_sec: clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600),
      timeout_sec: clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400),
      ...(refillPreferredChannel ? { channel: refillPreferredChannel } : {}),
    },
  }

  return {
    mode: 'adjust',
    subsystems: {
      ph: {
        enabled: true,
        targets: {
          min: phMin,
          max: phMax,
          target: round(phTarget, 2),
        },
      },
      ec: {
        enabled: true,
        targets: {
          min: ecMin,
          max: ecMax,
          target: round(ecTarget, 2),
        },
      },
      irrigation: {
        enabled: true,
        targets: {
          interval_minutes: irrigationIntervalMinutes,
          interval_sec: irrigationIntervalMinutes * 60,
          duration_seconds: irrigationDurationSeconds,
          duration_sec: irrigationDurationSeconds,
          ...(includeSystemType ? { system_type: waterForm.systemType } : {}),
          tanks_count: waterForm.tanksCount,
          fill_strategy: 'volume',
          correction_strategy: 'feedback_target',
          clean_tank_fill_l: clamp(Math.round(waterForm.cleanTankFillL), 10, 5000),
          nutrient_tank_target_l: clamp(Math.round(waterForm.nutrientTankTargetL), 10, 5000),
          irrigation_batch_l: clamp(Math.round(waterForm.irrigationBatchL), 1, 500),
          valve_switching_enabled: waterForm.valveSwitching,
          correction_during_irrigation: waterForm.correctionDuringIrrigation,
          fill_temperature_c: clamp(waterForm.fillTemperatureC, 5, 35),
          schedule: [
            {
              start: waterForm.fillWindowStart,
              end: waterForm.fillWindowEnd,
              action: 'fill_clean_tank_then_mix',
            },
          ],
          correction_node: {
            target_ph: round(phTarget, 2),
            target_ec: round(ecTarget, 2),
            sensors_location: 'correction_node',
          },
          drain_control: {
            enabled: waterForm.tanksCount === 3 ? waterForm.enableDrainControl : false,
            target_percent: waterForm.tanksCount === 3 ? clamp(waterForm.drainTargetPercent, 0, 100) : null,
          },
        },
      },
      climate: {
        enabled: climateForm.enabled,
        targets: {
          interval_sec: climateIntervalSec,
          temperature: {
            day: clamp(climateForm.dayTemp, 10, 35),
            night: clamp(climateForm.nightTemp, 10, 35),
          },
          humidity: {
            day: clamp(climateForm.dayHumidity, 30, 90),
            night: clamp(climateForm.nightHumidity, 30, 90),
          },
          vent_control: {
            role: 'vent',
            min_open_percent: clamp(Math.round(climateForm.ventMinPercent), 0, 100),
            max_open_percent: clamp(Math.round(climateForm.ventMaxPercent), 0, 100),
          },
          external_guard: {
            enabled: climateForm.useExternalTelemetry,
            temp_min: climateForm.outsideTempMin,
            temp_max: climateForm.outsideTempMax,
            humidity_max: climateForm.outsideHumidityMax,
          },
          schedule: [
            {
              start: climateForm.dayStart,
              end: climateForm.nightStart,
              profile: 'day',
            },
            {
              start: climateForm.nightStart,
              end: climateForm.dayStart,
              profile: 'night',
            },
          ],
          manual_override: {
            enabled: climateForm.manualOverrideEnabled,
            timeout_minutes: clamp(Math.round(climateForm.overrideMinutes), 5, 120),
          },
        },
      },
      lighting: {
        enabled: lightingForm.enabled,
        targets: {
          interval_sec: lightingIntervalSec,
          lux: {
            day: clamp(Math.round(lightingForm.luxDay), 0, 120000),
            night: clamp(Math.round(lightingForm.luxNight), 0, 120000),
          },
          photoperiod: {
            hours_on: clamp(lightingForm.hoursOn, 0, 24),
            hours_off: round(clamp(24 - lightingForm.hoursOn, 0, 24), 1),
          },
          schedule: [
            {
              start: lightingForm.scheduleStart,
              end: lightingForm.scheduleEnd,
            },
          ],
          future_metrics: {
            ppfd: null,
            dli: null,
            ready: true,
          },
        },
      },
      diagnostics: {
        enabled: waterForm.diagnosticsEnabled,
        targets: {
          interval_sec: diagnosticsIntervalSec,
          workflow: waterForm.cycleStartWorkflowEnabled ? 'cycle_start' : 'diagnostics',
          clean_tank_full_threshold: cleanTankFullThreshold,
          required_node_types: requiredNodeTypes,
          refill_duration_sec: clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600),
          refill_timeout_sec: clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400),
          refill: {
            duration_sec: clamp(Math.round(waterForm.refillDurationSeconds), 1, 3600),
            timeout_sec: clamp(Math.round(waterForm.refillTimeoutSeconds), 30, 86400),
            ...(refillPreferredChannel ? { channel: refillPreferredChannel } : {}),
          },
          execution: diagnosticsExecution,
        },
      },
      solution_change: {
        enabled: waterForm.solutionChangeEnabled,
        targets: {
          interval_sec: solutionChangeIntervalSec,
          duration_sec: solutionChangeDurationSec,
          execution: {
            duration_sec: solutionChangeDurationSec,
          },
        },
      },
    },
  }
}

export function resetToRecommended(forms: ZoneAutomationForms): void {
  const { climateForm, waterForm, lightingForm } = forms

  climateForm.enabled = true
  climateForm.dayTemp = 23
  climateForm.nightTemp = 20
  climateForm.dayHumidity = 62
  climateForm.nightHumidity = 70
  climateForm.intervalMinutes = 5
  climateForm.dayStart = '07:00'
  climateForm.nightStart = '19:00'
  climateForm.ventMinPercent = 15
  climateForm.ventMaxPercent = 85
  climateForm.useExternalTelemetry = true
  climateForm.outsideTempMin = 4
  climateForm.outsideTempMax = 34
  climateForm.outsideHumidityMax = 90
  climateForm.manualOverrideEnabled = true
  climateForm.overrideMinutes = 30

  waterForm.systemType = 'drip'
  waterForm.cleanTankFillL = 300
  waterForm.nutrientTankTargetL = 280
  waterForm.irrigationBatchL = 20
  waterForm.intervalMinutes = 30
  waterForm.durationSeconds = 120
  waterForm.fillTemperatureC = 20
  waterForm.fillWindowStart = '05:00'
  waterForm.fillWindowEnd = '07:00'
  waterForm.targetPh = 5.8
  waterForm.targetEc = 1.6
  waterForm.valveSwitching = true
  waterForm.correctionDuringIrrigation = true
  waterForm.enableDrainControl = false
  waterForm.drainTargetPercent = 20
  waterForm.diagnosticsEnabled = true
  waterForm.diagnosticsIntervalMinutes = 15
  waterForm.cycleStartWorkflowEnabled = true
  waterForm.cleanTankFullThreshold = 0.95
  waterForm.refillDurationSeconds = 30
  waterForm.refillTimeoutSeconds = 600
  waterForm.refillRequiredNodeTypes = 'irrig,climate,light'
  waterForm.refillPreferredChannel = 'fill_valve'
  waterForm.solutionChangeEnabled = false
  waterForm.solutionChangeIntervalMinutes = 180
  waterForm.solutionChangeDurationSeconds = 120
  waterForm.manualIrrigationSeconds = 90

  lightingForm.enabled = true
  lightingForm.luxDay = 18000
  lightingForm.luxNight = 0
  lightingForm.hoursOn = 16
  lightingForm.intervalMinutes = 30
  lightingForm.scheduleStart = '06:00'
  lightingForm.scheduleEnd = '22:00'
  lightingForm.manualIntensity = 75
  lightingForm.manualDurationHours = 4

  syncSystemToTankLayout(waterForm, 'drip')
}
