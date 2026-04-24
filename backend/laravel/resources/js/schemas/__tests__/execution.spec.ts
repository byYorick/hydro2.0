import { describe, expect, it } from 'vitest'
import { chainStepSchema, chainUpdatedEventSchema } from '../execution'

describe('chainStepSchema', () => {
  it('валидирует корректный шаг', () => {
    const result = chainStepSchema.safeParse({
      step: 'DISPATCH',
      at: '2026-02-10T12:34:07Z',
      ref: 'cmd-9931',
      detail: 'history-logger → MQTT',
      status: 'ok',
    })
    expect(result.success).toBe(true)
  })

  it('принимает optional live и at=null', () => {
    const result = chainStepSchema.safeParse({
      step: 'RUNNING',
      at: null,
      ref: 'ex-2042',
      detail: '',
      status: 'run',
      live: true,
    })
    expect(result.success).toBe(true)
  })

  it('отклоняет unknown step', () => {
    const result = chainStepSchema.safeParse({
      step: 'TOTALLY_INVALID',
      ref: 'x',
      detail: '',
      status: 'ok',
    })
    expect(result.success).toBe(false)
  })

  it('отклоняет unknown status', () => {
    const result = chainStepSchema.safeParse({
      step: 'DISPATCH',
      ref: 'cmd-1',
      detail: '',
      status: 'not-a-status',
    })
    expect(result.success).toBe(false)
  })
})

describe('chainUpdatedEventSchema', () => {
  it('валидирует полный payload', () => {
    const result = chainUpdatedEventSchema.safeParse({
      zone_id: 42,
      execution_id: '401',
      step: {
        step: 'DISPATCH',
        ref: 'cmd-1',
        detail: '',
        status: 'ok',
      },
      event_id: 100,
      server_ts: 1700000000,
    })
    expect(result.success).toBe(true)
  })
})
