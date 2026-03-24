import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { PumpCalibrationSettings } from '@/types/SystemSettings'

const authorityPumpCalibrationSettings = ref<Partial<PumpCalibrationSettings> | null>(null)
let authorityPumpCalibrationSettingsRequest: Promise<void> | null = null

export const DEFAULT_PUMP_CALIBRATION_SETTINGS: PumpCalibrationSettings = {
  ml_per_sec_min: 0.001,
  ml_per_sec_max: 1000,
  min_dose_ms: 1,
  calibration_duration_min_sec: 1,
  calibration_duration_max_sec: 60,
  quality_score_basic: 0.5,
  quality_score_with_k: 0.8,
  quality_score_legacy: 0.3,
  age_warning_days: 30,
  age_critical_days: 60,
  default_run_duration_sec: 20,
}

export function normalizePumpCalibrationSettings(
  raw: Partial<PumpCalibrationSettings> | null | undefined,
): PumpCalibrationSettings {
  return {
    ...DEFAULT_PUMP_CALIBRATION_SETTINGS,
    ...(raw ?? {}),
  }
}

export function usePumpCalibrationSettings() {
  const automationConfig = useAutomationConfig()

  if (authorityPumpCalibrationSettings.value === null && authorityPumpCalibrationSettingsRequest === null) {
    authorityPumpCalibrationSettingsRequest = automationConfig
      .getDocument<Partial<PumpCalibrationSettings>>('system', 0, 'system.pump_calibration_policy')
      .then((document) => {
        authorityPumpCalibrationSettings.value = document.payload ?? null
      })
      .catch(() => {})
      .finally(() => {
        authorityPumpCalibrationSettingsRequest = null
      })
  }

  return computed(() => normalizePumpCalibrationSettings(authorityPumpCalibrationSettings.value))
}
