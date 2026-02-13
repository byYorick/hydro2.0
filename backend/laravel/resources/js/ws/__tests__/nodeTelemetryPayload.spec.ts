import { describe, expect, it } from 'vitest'
import { parseNodeTelemetryBatch } from '../nodeTelemetryPayload'

describe('nodeTelemetryPayload', () => {
  it('нормализует batch updates с числовыми и строковыми полями', () => {
    const result = parseNodeTelemetryBatch({
      updates: [
        {
          node_id: '12',
          channel: 'temp_sensor',
          metric_type: 'TEMPERATURE',
          value: '23.4',
          ts: '1738920000000',
        },
      ],
    })

    expect(result).toEqual([
      {
        node_id: 12,
        channel: 'temp_sensor',
        metric_type: 'TEMPERATURE',
        value: 23.4,
        ts: 1738920000000,
      },
    ])
  })

  it('поддерживает одиночный payload и ts в ISO формате', () => {
    const result = parseNodeTelemetryBatch({
      node_id: 7,
      channel: null,
      metric_type: 'PH',
      value: 5.9,
      ts: '2026-02-07T13:20:00.000Z',
    })

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      node_id: 7,
      channel: null,
      metric_type: 'PH',
      value: 5.9,
    })
    expect(typeof result[0].ts).toBe('number')
    expect(Number.isFinite(result[0].ts)).toBe(true)
  })

  it('фильтрует невалидные элементы', () => {
    const result = parseNodeTelemetryBatch({
      updates: [
        { node_id: 1, metric_type: 'EC', value: 1.2, ts: 1000 },
        { node_id: null, metric_type: 'EC', value: 1.2, ts: 1001 },
        { node_id: 1, metric_type: null, value: 1.2, ts: 1002 },
        { node_id: 1, metric_type: 'EC', value: 'bad', ts: 1003 },
      ],
    })

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      node_id: 1,
      metric_type: 'EC',
      value: 1.2,
      ts: 1000,
    })
  })
})
