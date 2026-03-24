import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { ZoneProcessCalibrationForm } from '@/types/ProcessCalibration'
import type { ProcessCalibrationDefaultsSettings } from '@/types/SystemSettings'

const authorityProcessCalibrationDefaults = ref<Partial<ProcessCalibrationDefaultsSettings> | null>(null)
let authorityProcessCalibrationDefaultsRequest: Promise<void> | null = null

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
  const automationConfig = useAutomationConfig()
  if (authorityProcessCalibrationDefaults.value === null && authorityProcessCalibrationDefaultsRequest === null) {
    authorityProcessCalibrationDefaultsRequest = automationConfig
      .getDocument<Partial<ProcessCalibrationDefaultsSettings>>('system', 0, 'system.process_calibration_defaults')
      .then((document) => {
        authorityProcessCalibrationDefaults.value = document.payload ?? null
      })
      .catch(() => {})
      .finally(() => {
        authorityProcessCalibrationDefaultsRequest = null
      })
  }

  return computed(() => normalizeProcessCalibrationDefaults(authorityProcessCalibrationDefaults.value))
}
