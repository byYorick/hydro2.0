import { computed, type ComputedRef } from 'vue'
import { usePageProp } from '@/composables/usePageProps'
import type { ZoneProcessCalibrationForm } from '@/types/ProcessCalibration'
import type { ProcessCalibrationDefaultsSettings } from '@/types/SystemSettings'

export const FALLBACK_PROCESS_CALIBRATION_DEFAULTS: ProcessCalibrationDefaultsSettings = {
  ec_gain_per_ml: 0.11,
  ph_up_gain_per_ml: 0.08,
  ph_down_gain_per_ml: 0.07,
  ph_per_ec_ml: -0.015,
  ec_per_ph_ml: 0.02,
  transport_delay_sec: 20,
  settle_sec: 45,
  confidence: 0.75,
}

export function normalizeProcessCalibrationDefaults(
  raw: Partial<ProcessCalibrationDefaultsSettings> | null | undefined,
): ProcessCalibrationDefaultsSettings {
  return {
    ...FALLBACK_PROCESS_CALIBRATION_DEFAULTS,
    ...(raw ?? {}),
  }
}

export function createDefaultProcessCalibrationForm(
  defaults: ProcessCalibrationDefaultsSettings,
): ZoneProcessCalibrationForm {
  return {
    ec_gain_per_ml: String(defaults.ec_gain_per_ml),
    ph_up_gain_per_ml: String(defaults.ph_up_gain_per_ml),
    ph_down_gain_per_ml: String(defaults.ph_down_gain_per_ml),
    ph_per_ec_ml: String(defaults.ph_per_ec_ml),
    ec_per_ph_ml: String(defaults.ec_per_ph_ml),
    transport_delay_sec: String(defaults.transport_delay_sec),
    settle_sec: String(defaults.settle_sec),
    confidence: String(defaults.confidence),
  }
}

export function useProcessCalibrationDefaults() {
  let processCalibrationDefaults: ComputedRef<Partial<ProcessCalibrationDefaultsSettings> | null>
  try {
    processCalibrationDefaults = usePageProp<'processCalibrationDefaults', Partial<ProcessCalibrationDefaultsSettings> | null>(
      'processCalibrationDefaults',
    )
  } catch {
    processCalibrationDefaults = computed(() => null)
  }

  return computed(() => normalizeProcessCalibrationDefaults(processCalibrationDefaults.value))
}
