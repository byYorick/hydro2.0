import { describe, expect, it } from 'vitest'
import {
  coerceLegacyPhCalibrationPointPair,
  DEFAULT_SENSOR_CALIBRATION_SETTINGS,
  normalizeSensorCalibrationSettings,
} from '@/composables/useSensorCalibrationSettings'

describe('useSensorCalibrationSettings', () => {
  it('coerceLegacyPhCalibrationPointPair заменяет устаревшую пару 7 / 4.01', () => {
    const out = coerceLegacyPhCalibrationPointPair(7, 4.01)
    expect(out.p1).toBe(DEFAULT_SENSOR_CALIBRATION_SETTINGS.ph_point_1_value)
    expect(out.p2).toBe(DEFAULT_SENSOR_CALIBRATION_SETTINGS.ph_point_2_value)
  })

  it('normalizeSensorCalibrationSettings подтягивает эталоны из сырой политики с 7 / 4', () => {
    const n = normalizeSensorCalibrationSettings({ ph_point_1_value: 7, ph_point_2_value: 4 })
    expect(n.ph_point_1_value).toBe(4.01)
    expect(n.ph_point_2_value).toBe(9.18)
  })

  it('не трогает произвольные пары pH', () => {
    const n = normalizeSensorCalibrationSettings({ ph_point_1_value: 6.86, ph_point_2_value: 9.18 })
    expect(n.ph_point_1_value).toBe(6.86)
    expect(n.ph_point_2_value).toBe(9.18)
  })
})
