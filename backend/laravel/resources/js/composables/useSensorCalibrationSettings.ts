import { computed, ref } from 'vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const authoritySensorCalibrationSettings = ref<Partial<SensorCalibrationSettings> | null>(null)
let authoritySensorCalibrationSettingsRequest: Promise<void> | null = null

export const DEFAULT_SENSOR_CALIBRATION_SETTINGS: SensorCalibrationSettings = {
  ph_point_1_value: 4.01,
  ph_point_2_value: 9.18,
  ec_point_1_tds: 1413,
  ec_point_2_tds: 707,
  reminder_days: 30,
  critical_days: 90,
  command_timeout_sec: 10,
  ph_reference_min: 1,
  ph_reference_max: 14,
  ec_tds_reference_max: 10000,
}

/** Пара (7 / 4.01) — устаревшие дефолты политики; для Trema pH нужны два разных буфера (типично кислый + щелочной). */
export function coerceLegacyPhCalibrationPointPair(p1: number, p2: number): { p1: number; p2: number } {
  const legacy =
    p1 === 7 && (p2 === 4.01 || p2 === 4 || p2 === 4.0)
  if (legacy) {
    return {
      p1: DEFAULT_SENSOR_CALIBRATION_SETTINGS.ph_point_1_value,
      p2: DEFAULT_SENSOR_CALIBRATION_SETTINGS.ph_point_2_value,
    }
  }
  return { p1, p2 }
}

export function normalizeSensorCalibrationSettings(
  raw: Partial<SensorCalibrationSettings> | null | undefined,
): SensorCalibrationSettings {
  const merged: SensorCalibrationSettings = {
    ...DEFAULT_SENSOR_CALIBRATION_SETTINGS,
    ...(raw ?? {}),
  }

  const coerced = coerceLegacyPhCalibrationPointPair(merged.ph_point_1_value, merged.ph_point_2_value)
  merged.ph_point_1_value = coerced.p1
  merged.ph_point_2_value = coerced.p2

  return merged
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
