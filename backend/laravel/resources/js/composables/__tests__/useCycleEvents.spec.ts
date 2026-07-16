import { describe, expect, it } from 'vitest'

import {
  getEventMessage,
  getEventTypeLabel,
} from '../useCycleEvents'

describe('useCycleEvents labels', () => {
  it('переводит типы IRRIGATION_CYCLE_* на русский', () => {
    expect(getEventTypeLabel('IRRIGATION_CYCLE_STARTED')).toBe('Полив запущен')
    expect(getEventTypeLabel('IRRIGATION_CYCLE_FINISHED')).toBe('Полив завершён')
    expect(getEventTypeLabel('IRRIGATION_CYCLE_STOPPED')).toBe('Полив остановлен')
    expect(getEventTypeLabel('IRRIGATION_CYCLE_SKIPPED')).toBe('Полив пропущен')
  })

  it('предпочитает label из details вместо сырого type в message', () => {
    expect(getEventMessage({
      id: 1,
      type: 'IRRIGATION_CYCLE_STARTED',
      details: { label: 'Полив запущен' },
      message: 'IRRIGATION_CYCLE_STARTED',
      created_at: '2026-07-16T13:26:00Z',
    })).toBe('Полив запущен')

    expect(getEventMessage({
      id: 2,
      type: 'IRRIGATION_CYCLE_FINISHED',
      details: {},
      message: 'IRRIGATION_CYCLE_FINISHED',
      created_at: '2026-07-16T13:18:00Z',
    })).toBe('Полив завершён')
  })
})
