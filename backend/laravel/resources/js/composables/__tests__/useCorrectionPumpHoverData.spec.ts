import { describe, expect, it } from 'vitest'
import { buildCorrectionPumpHoverData } from '@/composables/useCorrectionPumpHoverData'

describe('buildCorrectionPumpHoverData', () => {
  it('показывает fallback без данных', () => {
    expect(buildCorrectionPumpHoverData(null)).toEqual({
      'Калибровка': 'нет данных',
      'PID': 'нет данных',
    })
  })

  it('собирает PID close и калибровку насоса', () => {
    const rows = buildCorrectionPumpHoverData({
      channel: 'pump_b',
      controller: 'ec',
      component: 'calcium',
      node_uid: 'nd-ec-1',
      ml_per_sec: 1.25,
      k_ms_per_ml_l: 12.5,
      kp: 0.4,
      ki: 0.05,
      kd: 0.01,
      dead_zone: 0.05,
      max_dose_ml: 8,
      min_interval_sec: 60,
    })

    expect(rows['Компонент']).toBe('calcium')
    expect(rows['мл/с']).toBe('1.25')
    expect(rows['PID (close)']).toContain('Kp=0.4')
    expect(rows['max_dose_ml']).toBe('8')
    expect(rows['min_interval_s']).toBe('60')
  })
})
