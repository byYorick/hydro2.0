import { describe, expect, it } from 'vitest'
import { formatSensorCalibrationPointError } from '@/utils/sensorCalibrationHumanError'

describe('formatSensorCalibrationPointError', () => {
  it('pH stage 2 calibration_failed — объясняет нестабильность Trema', () => {
    const msg = formatSensorCalibrationPointError('ph', 2, 'Failed to calibrate pH sensor', 'calibration_failed')
    expect(msg).toContain('Trema')
    expect(msg).toContain('Вторая точка')
  })

  it('учитывает только текст ошибки без кода', () => {
    const msg = formatSensorCalibrationPointError('ph', 2, 'Failed to calibrate pH sensor', null)
    expect(msg).toContain('Trema')
  })

  it('таймаут', () => {
    const msg = formatSensorCalibrationPointError('ec', 1, 'timed out', 'TIMEOUT')
    expect(msg).toContain('Таймаут')
  })

  it('незнакомая ошибка — оставляет текст узла', () => {
    const msg = formatSensorCalibrationPointError('ph', 1, 'weird_error_xyz', 'custom')
    expect(msg).toContain('weird_error_xyz')
  })
})
