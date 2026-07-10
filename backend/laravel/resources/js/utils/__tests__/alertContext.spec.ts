import { describe, expect, it } from 'vitest'
import {
  getAlertCorrectionWindowId,
  getAlertDetailsContextSummary,
  getAlertTaskId,
  zoneAlertsTabUrl,
} from '@/utils/alertContext'

describe('alertContext', () => {
  it('возвращает task_id из details по приоритету ключей', () => {
    expect(getAlertTaskId({ details: { task_id: 'task-1' } })).toBe('task-1')
    expect(getAlertTaskId({ details: { ae_task_id: 'ae-2' } })).toBe('ae-2')
    expect(getAlertTaskId({ details: { automation_task_id: 'auto-3' } })).toBe('auto-3')
    expect(getAlertTaskId({ details: { task_id: 'task-1', ae_task_id: 'ae-2' } })).toBe('task-1')
  })

  it('возвращает correction_window_id', () => {
    expect(getAlertCorrectionWindowId({ details: { correction_window_id: 'cw-42' } })).toBe('cw-42')
  })

  it('собирает краткий контекст error_code и stage', () => {
    expect(getAlertDetailsContextSummary({
      details: { error_code: 'ae3_timeout', stage: 'dose' },
    })).toBe('error: ae3_timeout · stage: dose')
  })

  it('строит deep-link на вкладку алертов зоны', () => {
    expect(zoneAlertsTabUrl(7)).toBe('/zones/7?tab=alerts')
  })
})
