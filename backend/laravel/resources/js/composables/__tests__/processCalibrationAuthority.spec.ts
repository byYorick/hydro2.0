import { describe, expect, it } from 'vitest'
import {
  buildEcComponentGainsPayload,
  extractEcComponentGainValue,
  normalizeEcComponentGains,
} from '@/composables/processCalibrationAuthority'

describe('processCalibrationAuthority ec_component_gains', () => {
  it('extractEcComponentGainValue принимает flat number и nested object', () => {
    expect(extractEcComponentGainValue(0.25)).toBe(0.25)
    expect(extractEcComponentGainValue('0.15')).toBe(0.15)
    expect(extractEcComponentGainValue({ ec_gain_per_ml: 0.12 })).toBe(0.12)
    expect(extractEcComponentGainValue(null)).toBeNull()
    expect(extractEcComponentGainValue({})).toBeNull()
  })

  it('normalizeEcComponentGains приводит flat к nested schema shape', () => {
    expect(
      normalizeEcComponentGains({
        calcium: 0.25,
        npk: 0.15,
        magnesium: null,
      }),
    ).toEqual({
      calcium: { ec_gain_per_ml: 0.25 },
      npk: { ec_gain_per_ml: 0.15 },
    })
  })

  it('normalizeEcComponentGains сохраняет уже nested shape', () => {
    expect(
      normalizeEcComponentGains({
        calcium: { ec_gain_per_ml: 0.25 },
        micro: { ec_gain_per_ml: 0.05 },
      }),
    ).toEqual({
      calcium: { ec_gain_per_ml: 0.25 },
      micro: { ec_gain_per_ml: 0.05 },
    })
  })

  it('normalizeEcComponentGains смешивает flat и nested в одном объекте', () => {
    expect(
      normalizeEcComponentGains({
        calcium: 0.25,
        npk: { ec_gain_per_ml: 0.15 },
      }),
    ).toEqual({
      calcium: { ec_gain_per_ml: 0.25 },
      npk: { ec_gain_per_ml: 0.15 },
    })
  })

  it('buildEcComponentGainsPayload пишет nested payload из формы', () => {
    expect(
      buildEcComponentGainsPayload({
        ec_component_gain_npk: '0.15',
        ec_component_gain_calcium: '0.25',
        ec_component_gain_magnesium: '',
        ec_component_gain_micro: '0.05',
      }),
    ).toEqual({
      npk: { ec_gain_per_ml: 0.15 },
      calcium: { ec_gain_per_ml: 0.25 },
      micro: { ec_gain_per_ml: 0.05 },
    })
  })

  it('buildEcComponentGainsPayload возвращает undefined если все поля пустые', () => {
    expect(
      buildEcComponentGainsPayload({
        ec_component_gain_npk: '',
        ec_component_gain_calcium: '',
        ec_component_gain_magnesium: '',
        ec_component_gain_micro: '',
      }),
    ).toBeUndefined()
  })
})
