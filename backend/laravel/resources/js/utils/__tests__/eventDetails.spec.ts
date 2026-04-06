import { describe, expect, it } from 'vitest'

import { buildEventDetails } from '../eventDetails'

describe('eventDetails', () => {
  it('показывает locked irrigation decision config для snapshot event', () => {
    const rows = buildEventDetails({
      id: 1,
      kind: 'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
      zone_id: 42,
      message: 'Decision snapshot locked',
      occurred_at: '2026-04-03T12:00:00Z',
      payload: {
        task_id: 401,
        strategy: 'smart_soil_v1',
        bundle_revision: 'bundle-live-1234567890',
        grow_cycle_id: 55,
        phase_name: 'veg',
        config: {
          lookback_sec: 1800,
          min_samples: 3,
          stale_after_sec: 600,
          hysteresis_pct: 2,
          spread_alert_threshold_pct: 7,
        },
      },
    })

    expect(rows).toEqual(expect.arrayContaining([
      { label: 'Lookback', value: '1800 с', variant: 'default' },
      { label: 'Min samples', value: '3', variant: 'default' },
      { label: 'Stale after', value: '600 с', variant: 'default' },
      { label: 'Hysteresis', value: '2%', variant: 'default' },
      { label: 'Spread alert', value: '7%', variant: 'default' },
    ]))
  })

  it('разворачивает поля PID_OUTPUT', () => {
    const rows = buildEventDetails({
      id: 2,
      kind: 'PID_OUTPUT',
      message: 'PID output',
      occurred_at: '2026-04-03T12:00:00Z',
      payload: {
        type: 'ph',
        zone_state: 'close',
        output: 5.5,
        error: 0.3,
        integral_term: 0.01,
        dt_seconds: 5,
        current: 6.3,
        target: 6.0,
        safety_skip_reason: 'none',
      },
    })

    expect(rows).toEqual([
      { label: 'Контур', value: 'PH', variant: 'default' },
      { label: 'Зона PID', value: 'close', variant: 'default' },
      { label: 'Текущее', value: '6.3000', variant: 'default' },
      { label: 'Цель', value: '6.0000', variant: 'default' },
      { label: 'Ошибка (e)', value: '0.3000', variant: 'default' },
      { label: 'Выход (u)', value: '5.5000 мл', variant: 'default' },
      { label: 'I-член', value: '0.0100', variant: 'default' },
      { label: 'Δt', value: '5 с', variant: 'default' },
      { label: 'Safety', value: 'none', variant: 'default' },
    ])
  })

  it('разворачивает поля PID_OUTPUT с P и D членами', () => {
    const rows = buildEventDetails({
      id: 5,
      kind: 'PID_OUTPUT',
      message: 'PID output',
      occurred_at: '2026-04-03T12:00:00Z',
      payload: {
        pid_type: 'ec',
        zone_state: 'far',
        output: 10.2,
        error: 0.5,
        proportional_term: 2.0,
        integral_term: 0.2,
        derivative_term: -0.05,
        dt_seconds: 10,
        current: 1.2,
        target: 1.8,
      },
    })

    expect(rows).toEqual(expect.arrayContaining([
      { label: 'Контур', value: 'EC', variant: 'default' },
      { label: 'Зона PID', value: 'far', variant: 'default' },
      { label: 'Текущее', value: '1.2000', variant: 'default' },
      { label: 'Цель', value: '1.8000', variant: 'default' },
      { label: 'Ошибка (e)', value: '0.5000', variant: 'default' },
      { label: 'Выход (u)', value: '10.2000 мл', variant: 'default' },
      { label: 'P-член', value: '2.0000', variant: 'default' },
      { label: 'I-член', value: '0.2000', variant: 'default' },
      { label: 'D-член', value: '-0.0500', variant: 'default' },
      { label: 'Δt', value: '10 с', variant: 'default' },
    ]))
  })

  it('разворачивает PID_CONFIG_UPDATED с полным конфигом', () => {
    const rows = buildEventDetails({
      id: 3,
      kind: 'PID_CONFIG_UPDATED',
      message: 'config',
      occurred_at: '2026-04-03T12:00:00Z',
      payload: {
        type: 'ec',
        updated_by: 7,
        old_config: {
          dead_zone: 0.05,
          close_zone: 0.2,
          far_zone: 0.5,
          max_integral: 20,
          zone_coeffs: {
            close: { kp: 1.0, ki: 0.1, kd: 0.0 },
            far: { kp: 3.0, ki: 0.3, kd: 0.0 },
          },
        },
        new_config: {
          dead_zone: 0.05,
          close_zone: 0.2,
          far_zone: 0.5,
          max_integral: 20,
          zone_coeffs: {
            close: { kp: 1.5, ki: 0.1, kd: 0.0 },
            far: { kp: 4.0, ki: 0.3, kd: 0.0 },
          },
        },
      },
    })

    expect(rows).toEqual(expect.arrayContaining([
      { label: 'Контур', value: 'EC', variant: 'default' },
      { label: 'Кто обновил', value: '7', variant: 'default' },
      { label: 'Было close', value: 'Kp=1  Ki=0.1  Kd=0', variant: 'default' },
      { label: 'Было far', value: 'Kp=3  Ki=0.3  Kd=0', variant: 'default' },
      { label: 'Стало close', value: 'Kp=1.5  Ki=0.1  Kd=0', variant: 'default' },
      { label: 'Стало far', value: 'Kp=4  Ki=0.3  Kd=0', variant: 'default' },
    ]))
  })

  it('разворачивает PID_CONFIG_UPDATED с fallback на JSON при неполном конфиге', () => {
    const rows = buildEventDetails({
      id: 4,
      kind: 'PID_CONFIG_UPDATED',
      message: 'config',
      occurred_at: '2026-04-03T12:00:00Z',
      payload: {
        type: 'ec',
        updated_by: 7,
        old_config: { kp: 1 },
        new_config: { kp: 1.2, ki: 0.01 },
      },
    })

    expect(rows).toEqual([
      { label: 'Контур', value: 'EC', variant: 'default' },
      { label: 'Кто обновил', value: '7', variant: 'default' },
      { label: 'Было', value: '{"kp":1}', variant: 'default' },
      { label: 'Стало', value: '{"kp":1.2,"ki":0.01}', variant: 'default' },
    ])
  })
})
