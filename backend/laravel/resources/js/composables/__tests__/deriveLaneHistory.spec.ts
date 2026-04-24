import { describe, expect, it } from 'vitest'
import { deriveLaneHistory } from '../deriveLaneHistory'
import type { ExecutionRun } from '../zoneScheduleWorkspaceTypes'

function run(overrides: Partial<ExecutionRun>): ExecutionRun {
  return {
    execution_id: 'ex',
    task_id: 't',
    zone_id: 1,
    task_type: 'irrigation',
    status: 'completed',
    created_at: '2026-02-10T12:00:00Z',
    ...overrides,
  }
}

describe('deriveLaneHistory', () => {
  const now = new Date('2026-02-10T12:00:00Z')

  it('группирует runs по task_type и расставляет % позиции в горизонте 24h', () => {
    const runs: ExecutionRun[] = [
      run({ execution_id: 'a', task_type: 'irrigation', created_at: '2026-02-10T06:00:00Z', status: 'completed' }),
      run({ execution_id: 'b', task_type: 'irrigation', created_at: '2026-02-10T12:00:00Z', status: 'running', is_active: true }),
      run({ execution_id: 'c', task_type: 'ph_correction', created_at: '2026-02-10T09:00:00Z', status: 'failed' }),
    ]
    const lanes = deriveLaneHistory(runs, '24h', now)
    const byLane = Object.fromEntries(lanes.map((l) => [l.lane, l.runs]))

    expect(byLane.irrigation).toHaveLength(2)
    expect(byLane.irrigation[0].t).toBe(25) // -6ч от сейчас при горизонте ±12ч → 25%
    expect(byLane.irrigation[0].s).toBe('ok')
    expect(byLane.irrigation[1].t).toBe(50)
    expect(byLane.irrigation[1].s).toBe('run')
    expect(byLane.ph_correction).toHaveLength(1)
    expect(byLane.ph_correction[0].s).toBe('err')
  })

  it('отбрасывает runs вне горизонта', () => {
    const runs: ExecutionRun[] = [
      run({ execution_id: 'far', created_at: '2026-02-09T00:00:00Z' }), // −36 ч
      run({ execution_id: 'ok', created_at: '2026-02-10T06:00:00Z' }),
    ]
    const lanes = deriveLaneHistory(runs, '24h', now)
    const bucket = lanes.find((l) => l.lane === 'irrigation')!
    expect(bucket.runs).toHaveLength(1)
  })

  it('маппит decision_outcome=skip на статус skip', () => {
    const runs: ExecutionRun[] = [
      run({
        execution_id: 's',
        status: 'completed',
        decision_outcome: 'skip',
        created_at: '2026-02-10T10:00:00Z',
      }),
    ]
    const lanes = deriveLaneHistory(runs, '24h', now)
    expect(lanes[0].runs[0].s).toBe('skip')
  })

  it('использует schedule_task_type как lane, если он задан', () => {
    const runs: ExecutionRun[] = [
      run({ task_type: 'irrigation', schedule_task_type: 'ph_correction' }),
    ]
    const lanes = deriveLaneHistory(runs, '24h', now)
    expect(lanes[0].lane).toBe('ph_correction')
  })
})
