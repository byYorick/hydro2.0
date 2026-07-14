import { describe, expect, it } from 'vitest'

import {
  buildOperatorStories,
  collapseNoisyEvents,
  isEngineerOnlyEvent,
  summarizeEventForOperator,
} from '../eventOperatorView'
import type { ZoneEvent } from '@/types/ZoneEvent'

function makeEvent(
  id: number,
  kind: string,
  message: string,
  payload: Record<string, unknown> = {},
  occurredAt = '2026-04-10T08:20:00Z',
): ZoneEvent {
  return {
    id,
    kind,
    zone_id: 7,
    message,
    occurred_at: occurredAt,
    payload,
  }
}

describe('eventOperatorView', () => {
  it('isEngineerOnlyEvent скрывает snapshot, PID и статусы команд', () => {
    expect(isEngineerOnlyEvent(makeEvent(1, 'IRR_STATE_SNAPSHOT', 'snap'))).toBe(true)
    expect(isEngineerOnlyEvent(makeEvent(2, 'PID_OUTPUT', 'pid'))).toBe(true)
    expect(isEngineerOnlyEvent(makeEvent(3, 'command_status', 'ack'))).toBe(true)
    expect(isEngineerOnlyEvent(makeEvent(4, 'CORRECTION_SKIPPED_COOLDOWN', 'skip'))).toBe(true)
    expect(isEngineerOnlyEvent(makeEvent(5, 'COMMAND_TIMEOUT', 'timeout'))).toBe(false)
    expect(isEngineerOnlyEvent(makeEvent(6, 'CORRECTION_SKIPPED_EMERGENCY_STOP', 'estop'))).toBe(false)
    expect(isEngineerOnlyEvent(makeEvent(7, 'EC_DOSING', 'dose'))).toBe(false)
  })

  it('collapseNoisyEvents схлопывает повторы snapshot', () => {
    const items = collapseNoisyEvents([
      makeEvent(3, 'IRR_STATE_SNAPSHOT', 'a', {}, '2026-04-10T08:20:03Z'),
      makeEvent(2, 'IRR_STATE_SNAPSHOT', 'b', {}, '2026-04-10T08:20:02Z'),
      makeEvent(1, 'IRR_STATE_SNAPSHOT', 'c', {}, '2026-04-10T08:20:01Z'),
      makeEvent(4, 'ALERT_CREATED', 'alert', { code: 'pump' }, '2026-04-10T08:20:04Z'),
    ])

    expect(items[0]).toMatchObject({ type: 'event' })
    expect(items[1]).toMatchObject({
      type: 'collapsed',
      kind: 'IRR_STATE_SNAPSHOT',
      count: 3,
    })
  })

  it('buildOperatorStories даёт человеческий summary correction-цепочки', () => {
    const stories = buildOperatorStories([
      makeEvent(1, 'CORRECTION_DECISION_MADE', 'Decision', {
        task_id: 28,
        correction_window_id: 'task:28:irrigating:irrigation_check',
        selected_action: 'ec',
        current_ec: 1.1,
      }, '2026-04-10T08:20:00Z'),
      makeEvent(2, 'EC_DOSING', 'Dose', {
        task_id: 28,
        correction_window_id: 'task:28:irrigating:irrigation_check',
        dose_ml: 12,
        channel: 'A+B',
      }, '2026-04-10T08:20:10Z'),
      makeEvent(3, 'CORRECTION_ACTION_DEFERRED', 'Wait', {
        task_id: 28,
        correction_window_id: 'task:28:irrigating:irrigation_check',
      }, '2026-04-10T08:20:20Z'),
      makeEvent(4, 'IRR_STATE_SNAPSHOT', 'noise', {
        task_id: 28,
        correction_window_id: 'task:28:irrigating:irrigation_check',
      }, '2026-04-10T08:20:15Z'),
      makeEvent(5, 'PID_OUTPUT', 'pid', {
        task_id: 28,
        correction_window_id: 'task:28:irrigating:irrigation_check',
      }, '2026-04-10T08:20:12Z'),
    ])

    expect(stories).toHaveLength(1)
    expect(stories[0].title).toBe('Коррекция EC')
    expect(stories[0].summary).toContain('EC вне цели')
    expect(stories[0].summary).toContain('Дозирование')
    expect(stories[0].summary).toContain('Ожидание')
    expect(stories[0].eventIds).not.toContain(4)
    expect(stories[0].collapsedNoise?.some((item) => item.label.includes('PID') || item.count >= 1)).toBe(true)
  })

  it('summarizeEventForOperator даёт короткие фразы полива и тревог', () => {
    expect(summarizeEventForOperator(makeEvent(1, 'IRRIGATION_CYCLE_STARTED', 'x'))).toBe('Полив начат')
    expect(summarizeEventForOperator(makeEvent(2, 'IRRIGATION_CYCLE_FINISHED', 'x'))).toBe('Полив завершён')
    expect(summarizeEventForOperator(makeEvent(3, 'ALERT_CREATED', 'x', { code: 'насос не ответил' }))).toBe(
      'Тревога: насос не ответил',
    )
  })
})
