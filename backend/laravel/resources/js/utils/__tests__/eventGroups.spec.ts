import { describe, expect, it } from 'vitest'

import { groupZoneEvents } from '../eventGroups'

describe('eventGroups', () => {
  it('группирует runtime events по correction window и task id', () => {
    const groups = groupZoneEvents([
      {
        id: 11,
        kind: 'EC_DOSING',
        zone_id: 7,
        message: 'EC дозирование',
        occurred_at: '2026-04-10T08:20:25Z',
        payload: {
          task_id: 28,
          correction_window_id: 'task:28:irrigating:irrigation_check',
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
          snapshot_event_id: 1699,
        },
      },
      {
        id: 10,
        kind: 'CORRECTION_DECISION_MADE',
        zone_id: 7,
        message: 'Decision made',
        occurred_at: '2026-04-10T08:20:20Z',
        payload: {
          task_id: 28,
          correction_window_id: 'task:28:irrigating:irrigation_check',
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
        },
      },
      {
        id: 9,
        kind: 'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
        zone_id: 7,
        message: 'Snapshot locked',
        occurred_at: '2026-04-10T08:20:10Z',
        payload: {
          task_id: 28,
          workflow_phase: 'irrigating',
          stage: 'irrigation_check',
        },
      },
    ])

    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      id: 'correction_window:task:28:irrigating:irrigation_check',
      title: 'AE задача #28 · Окно irrigation_check',
      subtitle: 'irrigating / irrigation_check',
      badge: '2 события',
      isCorrelated: true,
    })
    expect(groups[0].events.map((event) => event.id)).toEqual([11, 10])
    expect(groups[1]).toMatchObject({
      id: 'task:28',
      title: 'AE задача #28',
      subtitle: 'irrigating / irrigation_check',
      badge: '1 событие',
      isCorrelated: true,
    })
  })

  it('оставляет несвязанные события отдельными группами', () => {
    const groups = groupZoneEvents([
      {
        id: 1,
        kind: 'ALERT_CREATED',
        zone_id: 5,
        message: 'Alert',
        occurred_at: '2026-04-10T08:00:00Z',
        payload: { severity: 'critical' },
      },
      {
        id: 2,
        kind: 'NODE_CONNECTED',
        zone_id: 5,
        message: 'Node connected',
        occurred_at: '2026-04-10T08:01:00Z',
        payload: { node_uid: 'nd-test-irrig-1' },
      },
    ])

    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      id: 'event:2',
      title: 'Узел подключён',
      isCorrelated: false,
    })
    expect(groups[1]).toMatchObject({
      id: 'event:1',
      title: 'Тревога создана',
      isCorrelated: false,
    })
  })
})
