import { describe, expect, it } from 'vitest'
import { parseZoneUpdatePayload } from '../zoneUpdatePayload'

describe('zoneUpdatePayload', () => {
  it('нормализует id и числовые telemetry-поля', () => {
    const parsed = parseZoneUpdatePayload({
      id: '42',
      telemetry: {
        ph: '5.8',
        ec: 1.4,
        temperature: '24',
        humidity: 55,
      },
    })

    expect(parsed).toEqual({
      zoneId: 42,
      telemetry: {
        ph: 5.8,
        ec: 1.4,
        temperature: 24,
        humidity: 55,
      },
    })
  })

  it('игнорирует нечисловые значения telemetry', () => {
    const parsed = parseZoneUpdatePayload({
      id: 7,
      telemetry: {
        ph: 'bad',
        ec: null,
        temperature: undefined,
        humidity: '  ',
      },
    })

    expect(parsed).toEqual({
      zoneId: 7,
      telemetry: undefined,
    })
  })

  it('возвращает пустой объект для невалидного payload', () => {
    expect(parseZoneUpdatePayload(null)).toEqual({})
    expect(parseZoneUpdatePayload('invalid')).toEqual({})
  })
})
