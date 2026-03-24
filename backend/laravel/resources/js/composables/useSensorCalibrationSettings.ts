import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const authoritySensorCalibrationSettings = ref<Partial<SensorCalibrationSettings> | null>(null)
let authoritySensorCalibrationSettingsRequest: Promise<void> | null = null

export const DEFAULT_SENSOR_CALIBRATION_SETTINGS: SensorCalibrationSettings = {
  ph_point_1_value: 7,
  ph_point_2_value: 4.01,
  ec_point_1_tds: 1413,
  ec_point_2_tds: 707,
  reminder_days: 30,
  critical_days: 90,
  command_timeout_sec: 10,
  ph_reference_min: 1,
  ph_reference_max: 12,
  ec_tds_reference_max: 10000,
}

export function normalizeSensorCalibrationSettings(
  raw: Partial<SensorCalibrationSettings> | null | undefined,
): SensorCalibrationSettings {
  return {
    ...DEFAULT_SENSOR_CALIBRATION_SETTINGS,
    ...(raw ?? {}),
  }
}

export function useSensorCalibrationSettings() {
  const automationConfig = useAutomationConfig()

  if (authoritySensorCalibrationSettings.value === null && authoritySensorCalibrationSettingsRequest === null) {
    authoritySensorCalibrationSettingsRequest = automationConfig
      .getDocument<Partial<SensorCalibrationSettings>>('system', 0, 'system.sensor_calibration_policy')
      .then((document) => {
        authoritySensorCalibrationSettings.value = document.payload ?? null
      })
      .catch(() => {})
      .finally(() => {
        authoritySensorCalibrationSettingsRequest = null
      })
  }

  return computed(() => normalizeSensorCalibrationSettings(authoritySensorCalibrationSettings.value))
}
