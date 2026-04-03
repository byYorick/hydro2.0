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
})
